import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.agent_modules import Summarizer, ToolManager
from tests.fixtures.summarizer_data import (
    get_mock_long_content,
    get_mock_short_content,
    get_mock_tool_result_content,
    get_mock_summary_response,
    get_mock_title_response,
    get_mock_messages_for_title,
    get_mock_llm_summary_response,
    get_mock_llm_title_response
)


@pytest.fixture
def mock_summarizer():
    """
    Pytest fixture som oppretter en Summarizer med mocket LLM.

    Eksempel bruk:
    def test_something(mock_summarizer):
        # mock_summarizer er allerede konfigurert med mocket LLM
        pass
    """
    with patch('agent.agent_modules.init_chat_model') as mock_init:
        mock_llm = MagicMock()
        mock_init.return_value = mock_llm

        summarizer = Summarizer(model_name="gpt-4o-mini", model_provider="openai")
        summarizer.model = mock_llm

        yield summarizer


@pytest.fixture
def mock_tool_manager():
    """
    Pytest fixture som oppretter en ToolManager.

    Eksempel bruk:
    def test_something(mock_tool_manager):
        # mock_tool_manager er klar til bruk
        pass
    """
    return ToolManager()


# ============================================
#           SUMMARIZER TESTS
# ============================================

def test_summarizer_init():
    """Test Summarizer initialization with default parameters."""
    with patch('agent.agent_modules.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        summarizer = Summarizer()

        mock_init.assert_called_once_with("gpt-4o-mini", model_provider="openai", temperature=0)
        assert summarizer.model is not None


def test_summarizer_init_custom_model():
    """Test Summarizer initialization with custom model."""
    with patch('agent.agent_modules.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        summarizer = Summarizer(model_name="gpt-4o", model_provider="openai")

        mock_init.assert_called_once_with("gpt-4o", model_provider="openai", temperature=0)
        assert summarizer.model is not None


def test_summarize_short_content(mock_summarizer):
    """Test summarize with short content (no truncation needed)."""
    content = get_mock_short_content()
    mock_summarizer.model.invoke.return_value = get_mock_llm_summary_response()

    result = mock_summarizer.summarize(content)

    mock_summarizer.model.invoke.assert_called_once()
    call_args = mock_summarizer.model.invoke.call_args[0][0]
    assert "Summarize the this data in MAX 200-400 tokens" in call_args
    assert content in call_args
    assert result == get_mock_summary_response()


def test_summarize_long_content_with_limit(mock_summarizer):
    """Test summarize with long content and token limit triggers truncation."""
    content = get_mock_long_content()
    limit = 100  # Small limit to trigger truncation
    mock_summarizer.model.invoke.return_value = get_mock_llm_summary_response()

    result = mock_summarizer.summarize(content, limit=limit)

    mock_summarizer.model.invoke.assert_called_once()
    call_args = mock_summarizer.model.invoke.call_args[0][0]
    # Should use truncated version when content exceeds limit
    assert "Summarize the this data in 200-400 tokens" in call_args
    assert "..." in call_args  # Should have truncation indicator
    assert result == get_mock_summary_response()


def test_summarize_content_under_limit(mock_summarizer):
    """Test summarize with content under limit does not truncate."""
    content = "Short content"
    limit = 1000  # Large limit
    mock_summarizer.model.invoke.return_value = get_mock_llm_summary_response()

    result = mock_summarizer.summarize(content, limit=limit)

    call_args = mock_summarizer.model.invoke.call_args[0][0]
    # Should use MAX version (no truncation)
    assert "MAX 200-400 tokens" in call_args
    assert result == get_mock_summary_response()


def test_summarize_no_content_attribute(mock_summarizer):
    """Test summarize handles response without content attribute."""
    content = "Test content"
    # Return object without content attribute
    mock_response = "String response without content attribute"
    mock_summarizer.model.invoke.return_value = mock_response

    result = mock_summarizer.summarize(content)

    assert result == str(mock_response)


def test_mk_title(mock_summarizer):
    """Test mk_title generates title from messages."""
    messages = get_mock_messages_for_title()
    mock_summarizer.model.invoke.return_value = get_mock_llm_title_response()

    result = mock_summarizer.mk_title(messages)

    mock_summarizer.model.invoke.assert_called_once()
    call_args = mock_summarizer.model.invoke.call_args[0][0]
    assert "Make a short title" in call_args
    assert "2-5 words" in call_args
    assert "MAX 5 words" in call_args
    assert result == get_mock_title_response()


def test_mk_title_with_company(mock_summarizer):
    """Test mk_title includes company name when present."""
    messages = [
        {"type": "human", "content": "I need help with Acme Corp case"},
        {"type": "ai", "content": "I'll help you with the Acme Corp case"}
    ]
    mock_summarizer.model.invoke.return_value = get_mock_llm_title_response()

    result = mock_summarizer.mk_title(messages)

    call_args = mock_summarizer.model.invoke.call_args[0][0]
    assert "Use company if present" in call_args
    assert result == get_mock_title_response()


def test_summarize_tool_result(mock_summarizer):
    """Test summarize with tool result content."""
    content = get_mock_tool_result_content()
    mock_summarizer.model.invoke.return_value = get_mock_llm_summary_response()

    result = mock_summarizer.summarize(content)

    mock_summarizer.model.invoke.assert_called_once()
    assert result == get_mock_summary_response()


def test_summarize_empty_content(mock_summarizer):
    """Test summarize with empty content."""
    content = ""
    mock_summarizer.model.invoke.return_value = get_mock_llm_summary_response()

    result = mock_summarizer.summarize(content)

    mock_summarizer.model.invoke.assert_called_once()
    assert result is not None


def test_summarize_none_limit(mock_summarizer):
    """Test summarize with None limit parameter."""
    content = get_mock_long_content()
    mock_summarizer.model.invoke.return_value = get_mock_llm_summary_response()

    result = mock_summarizer.summarize(content, limit=None)

    call_args = mock_summarizer.model.invoke.call_args[0][0]
    # Should use MAX version (no truncation) when limit is None
    assert "MAX 200-400 tokens" in call_args
    assert result == get_mock_summary_response()


# ============================================
#           TOOL MANAGER TESTS
# ============================================

def test_tool_manager_init(mock_tool_manager):
    """Test ToolManager initialization."""
    assert mock_tool_manager is not None


def test_format_tool_result_dict(mock_tool_manager):
    """Test format_tool_result with dict input."""
    result = {"key": "value", "number": 123}

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == '{"key": "value", "number": 123}'


def test_format_tool_result_list(mock_tool_manager):
    """Test format_tool_result with list input."""
    result = [{"id": 1}, {"id": 2}]

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == '[{"id": 1}, {"id": 2}]'


def test_format_tool_result_string(mock_tool_manager):
    """Test format_tool_result with string input."""
    result = "Simple string result"

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == "Simple string result"


def test_format_tool_result_number(mock_tool_manager):
    """Test format_tool_result with number input."""
    result = 42

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == "42"


def test_format_tool_result_none(mock_tool_manager):
    """Test format_tool_result with None input."""
    result = None

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == "None"


def test_format_tool_result_nested_dict(mock_tool_manager):
    """Test format_tool_result with nested dict."""
    result = {
        "outer": {
            "inner": {
                "value": "nested"
            }
        }
    }

    formatted = mock_tool_manager.format_tool_result(result)

    assert "nested" in formatted
    assert "inner" in formatted


def test_format_tool_result_with_unicode(mock_tool_manager):
    """Test format_tool_result preserves unicode characters."""
    result = {"name": "Petter Nordmann", "message": "Hei på deg!"}

    formatted = mock_tool_manager.format_tool_result(result)

    assert "Petter Nordmann" in formatted
    assert "Hei på deg!" in formatted


def test_format_tool_result_non_serializable(mock_tool_manager):
    """Test format_tool_result with non-JSON-serializable object."""

    class CustomObject:
        def __str__(self):
            return "CustomObject representation"

    result = CustomObject()

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == "CustomObject representation"


def test_format_tool_result_list_with_non_serializable(mock_tool_manager):
    """Test format_tool_result with list containing non-serializable object."""

    class CustomObject:
        def __str__(self):
            return "CustomObject"

    result = [CustomObject(), "string"]

    formatted = mock_tool_manager.format_tool_result(result)

    # Should fall back to str() conversion
    assert "CustomObject" in formatted or "string" in formatted


def test_format_tool_result_empty_dict(mock_tool_manager):
    """Test format_tool_result with empty dict."""
    result = {}

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == "{}"


def test_format_tool_result_empty_list(mock_tool_manager):
    """Test format_tool_result with empty list."""
    result = []

    formatted = mock_tool_manager.format_tool_result(result)

    assert formatted == "[]"


# ============================================
#           INTEGRATION-LIKE TESTS
# ============================================

def test_summarizer_model_invocation_error(mock_summarizer):
    """Test summarize handles model invocation errors."""
    content = "Test content"
    mock_summarizer.model.invoke.side_effect = Exception("API Error")

    with pytest.raises(Exception) as exc_info:
        mock_summarizer.summarize(content)

    assert "API Error" in str(exc_info.value)


def test_mk_title_model_invocation_error(mock_summarizer):
    """Test mk_title handles model invocation errors."""
    messages = get_mock_messages_for_title()
    mock_summarizer.model.invoke.side_effect = Exception("API Error")

    with pytest.raises(Exception) as exc_info:
        mock_summarizer.mk_title(messages)

    assert "API Error" in str(exc_info.value)
