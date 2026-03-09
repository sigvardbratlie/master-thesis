"""Tests for agent utils: config_utils and logging_utils."""
import logging
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.config_utils import (
    AppConfig,
    AsyncConfig,
    ConsoleLoggingConfig,
    FileLoggingConfig,
    LoggingConfig,
)
from utils.logging_utils import setup_logging


# ── FileLoggingConfig ─────────────────────────────────────────────────────────


class TestFileLoggingConfig:
    def test_defaults(self):
        c = FileLoggingConfig()
        assert c.enabled is False
        assert c.level == "info"
        assert c.path == "logs/app.log"

    def test_custom_values(self):
        c = FileLoggingConfig(enabled=True, level="debug", path="/tmp/app.log")
        assert c.enabled is True
        assert c.level == "debug"
        assert c.path == "/tmp/app.log"


# ── ConsoleLoggingConfig ──────────────────────────────────────────────────────


class TestConsoleLoggingConfig:
    def test_defaults(self):
        c = ConsoleLoggingConfig()
        assert c.enabled is True
        assert c.level == "info"

    def test_disable_console(self):
        c = ConsoleLoggingConfig(enabled=False)
        assert c.enabled is False


# ── LoggingConfig ─────────────────────────────────────────────────────────────


class TestLoggingConfig:
    def test_defaults(self):
        c = LoggingConfig()
        assert c.level == "info"
        assert isinstance(c.file, FileLoggingConfig)
        assert isinstance(c.console, ConsoleLoggingConfig)

    def test_nested_override(self):
        c = LoggingConfig(level="debug", file=FileLoggingConfig(enabled=True))
        assert c.level == "debug"
        assert c.file.enabled is True


# ── AsyncConfig ───────────────────────────────────────────────────────────────


class TestAsyncConfig:
    def test_defaults(self):
        c = AsyncConfig()
        assert c.max_concurrent_requests == 20
        assert c.throttle_value == 0.0

    def test_custom(self):
        c = AsyncConfig(max_concurrent_requests=5, throttle_value=1.5)
        assert c.max_concurrent_requests == 5
        assert c.throttle_value == 1.5


# ── AppConfig ─────────────────────────────────────────────────────────────────


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert isinstance(config.logging, LoggingConfig)
        assert isinstance(config.async_tasks, AsyncConfig)
        assert config.logging.level == "info"
        assert config.async_tasks.max_concurrent_requests == 20

    def test_from_toml_valid(self):
        toml_content = textwrap.dedent("""\
            [logging]
            level = "debug"

            [logging.file]
            enabled = true
            level = "debug"
            path = "/tmp/test.log"

            [logging.console]
            enabled = true
            level = "debug"

            [async]
            max_concurrent_requests = 10
            throttle_value = 0.5
        """)
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml_content)
            tmp_path = f.name

        config = AppConfig.from_toml(tmp_path)
        assert config.logging.level == "debug"
        assert config.logging.file.enabled is True
        assert config.logging.file.path == "/tmp/test.log"
        assert config.async_tasks.max_concurrent_requests == 10
        assert config.async_tasks.throttle_value == 0.5

    def test_from_toml_missing_file_returns_defaults(self, capsys):
        config = AppConfig.from_toml("/nonexistent/path/config.toml")
        assert isinstance(config, AppConfig)
        assert config.logging.level == "info"
        captured = capsys.readouterr()
        assert "Warning" in captured.out

    def test_from_toml_partial_config(self):
        """Missing sections fall back to defaults."""
        toml_content = "[logging]\nlevel = \"warning\"\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml_content)
            tmp_path = f.name

        config = AppConfig.from_toml(tmp_path)
        assert config.logging.level == "warning"
        assert config.async_tasks.max_concurrent_requests == 20  # default

    def test_from_toml_accepts_pathlib_path(self):
        toml_content = "[logging]\nlevel = \"info\"\n[async]\nmax_concurrent_requests = 5\nthrottle_value = 0.0\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml_content)
            tmp_path = Path(f.name)

        config = AppConfig.from_toml(tmp_path)
        assert config.async_tasks.max_concurrent_requests == 5


# ── setup_logging ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clean_root_logger():
    """Remove handlers added during each test to avoid cross-test pollution."""
    root = logging.root
    original_handlers = root.handlers[:]
    yield
    root.handlers = original_handlers


class TestSetupLogging:
    def test_console_handler_added_when_enabled(self):
        config = AppConfig(logging=LoggingConfig(console=ConsoleLoggingConfig(enabled=True)))
        before = len(logging.root.handlers)
        setup_logging(config)
        after = len(logging.root.handlers)
        assert after == before + 1
        assert any(isinstance(h, logging.StreamHandler) for h in logging.root.handlers)

    def test_no_console_handler_when_disabled(self):
        config = AppConfig(logging=LoggingConfig(console=ConsoleLoggingConfig(enabled=False)))
        before_count = len(logging.root.handlers)
        before_types = [type(h) for h in logging.root.handlers]
        setup_logging(config)
        stream_handlers_after = [h for h in logging.root.handlers if type(h) is logging.StreamHandler]
        stream_handlers_before = [h for h in logging.root.handlers[:before_count] if type(h) is logging.StreamHandler]
        assert len(stream_handlers_after) == len(stream_handlers_before)

    def test_file_handler_added_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "test.log")
            config = AppConfig(
                logging=LoggingConfig(
                    console=ConsoleLoggingConfig(enabled=False),
                    file=FileLoggingConfig(enabled=True, level="debug", path=log_path),
                )
            )
            setup_logging(config)
            from logging.handlers import RotatingFileHandler
            assert any(isinstance(h, RotatingFileHandler) for h in logging.root.handlers)

    def test_no_file_handler_when_disabled(self):
        from logging.handlers import RotatingFileHandler
        config = AppConfig(
            logging=LoggingConfig(
                console=ConsoleLoggingConfig(enabled=False),
                file=FileLoggingConfig(enabled=False),
            )
        )
        setup_logging(config)
        assert not any(isinstance(h, RotatingFileHandler) for h in logging.root.handlers)

    def test_root_logger_level_set_to_debug(self):
        config = AppConfig()
        setup_logging(config)
        assert logging.root.level == logging.DEBUG

    def test_console_level_respected(self):
        config = AppConfig(
            logging=LoggingConfig(
                console=ConsoleLoggingConfig(enabled=True, level="warning"),
            )
        )
        setup_logging(config)
        stream_handlers = [h for h in logging.root.handlers if type(h) is logging.StreamHandler]
        assert any(h.level == logging.WARNING for h in stream_handlers)

    def test_file_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "subdir" / "nested" / "test.log")
            config = AppConfig(
                logging=LoggingConfig(
                    console=ConsoleLoggingConfig(enabled=False),
                    file=FileLoggingConfig(enabled=True, path=log_path),
                )
            )
            setup_logging(config)
            assert Path(log_path).parent.exists()
