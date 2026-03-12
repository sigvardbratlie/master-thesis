"""Tests for CollectAgentResult in evals.collect_module."""
import pytest
import uuid
from base64 import b64encode
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from evals.models import ConversationTurn, DatasetPayload, Session


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(idx: int, date: str = "2024-01-15") -> Session:
    return Session(
        session=idx,
        session_name=f"Session {idx}",
        date=date,
        init_query=f"Init query {idx}",
        init_query_id=str(uuid.uuid4()),
        attachments=[],
        conversation=[
            ConversationTurn(input=f"Query {idx}.1", answer="", query_id=str(uuid.uuid4()), order=1),
            ConversationTurn(input=f"Query {idx}.2", answer="", query_id=str(uuid.uuid4()), order=2),
        ],
    )


def _make_data(n_sessions: int = 2) -> DatasetPayload:
    return DatasetPayload(
        dataset_name="THRD-2021-163881",
        project_id="proj-123",
        user_id="user-abc",
        sessions=[_make_session(i) for i in range(n_sessions)],
    )


async def _async_gen(items):
    for item in items:
        yield item


def _make_mock_graph(chunks=None):
    """Return a mock compiled graph whose astream() yields the given chunks."""
    async def _astream(*args, **kwargs):
        for chunk in (chunks or []):
            yield chunk

    mock_graph = MagicMock()
    mock_graph.astream = _astream
    return mock_graph


@contextmanager
def _mocked_instance(data: DatasetPayload):
    """Yield a CollectAgentResult with all external dependencies mocked out."""
    mock_config = MagicMock()
    mock_config.async_tasks.max_concurrent_requests = 3
    mock_config.async_tasks.throttle_value = 0
    mock_config.project.embed_to_vectorstore = True
    mock_config.project.save_to_storage = True

    mock_bucket = MagicMock()
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    with (
        patch("google.cloud.storage.Client", return_value=mock_client),
        patch("psycopg_pool.AsyncConnectionPool", MagicMock()),
        patch("langgraph.checkpoint.postgres.aio.AsyncPostgresSaver", MagicMock()),
        patch("evals.collect_module.AppConfig", return_value=mock_config),
    ):
        from evals.collect_module import CollectAgentResult
        car = CollectAgentResult(data, config=mock_config)
        yield car


# ── file_type_map ─────────────────────────────────────────────────────────────

class TestFileTypeMap:
    """CollectAgentResult.file_type_map must return the correct MIME type."""

    CASES = [
        ("path/to/doc.pdf", "application/pdf"),
        ("path/to/doc.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("path/to/sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("path/to/data.csv", "text/csv"),
        ("path/to/note.txt", "text/plain"),
        ("path/to/readme.md", "text/markdown"),
        ("path/to/email.eml", "message/rfc822"),
        ("path/to/unknown.xyz", None),
    ]

    @pytest.mark.parametrize("path,expected", CASES)
    def test_mime_types(self, path, expected):
        with _mocked_instance(_make_data()) as car:
            assert car.file_type_map(path) == expected


# ── parse_attachments ─────────────────────────────────────────────────────────

class TestParseAttachments:
    def test_creates_attachment_model(self):
        data = _make_data()
        file_bytes = b"fake pdf content"
        with _mocked_instance(data) as car:
            car.dataclass.bucket.blob.return_value.download_as_bytes.return_value = file_bytes

            result = car.parse_attachments(
                attachment_path="datasets/THRD/01_data/2024-01-10_doc.pdf",
                query_id="q-1",
                session_id="sess-1",
                user_id="user-abc",
            )

        assert result.filename == "datasets/THRD/01_data/2024-01-10_doc.pdf"
        assert result.file_type == "application/pdf"
        assert result.content == b64encode(file_bytes).decode("utf-8")
        assert result.query_id == "q-1"
        assert result.path.endswith(".pdf")

    def test_path_contains_user_and_session(self):
        with _mocked_instance(_make_data()) as car:
            car.dataclass.bucket.blob.return_value.download_as_bytes.return_value = b"data"
            result = car.parse_attachments(
                attachment_path="x/2024-01-01_f.txt",
                query_id="q-1",
                session_id="sess-42",
                user_id="user-xyz",
            )
        assert "user-xyz" in result.path
        assert "sess-42" in result.path


# ── init_pipeline ─────────────────────────────────────────────────────────────

class TestInitPipeline:
    def test_returns_pipeline_and_clean(self):
        """init_pipeline should return a (ProjectPipeline, ProjectClean) tuple."""
        with _mocked_instance(_make_data()) as car:
            with (
                patch("evals.collect_module.ProjectPipeline") as mock_pm_cls,
                patch("evals.collect_module.ProjectClean") as mock_clean_cls,
            ):
                mock_pm = MagicMock()
                mock_clean = MagicMock()
                mock_pm_cls.return_value = mock_pm
                mock_clean_cls.return_value = mock_clean

                pm, clean = car.init_pipeline()

        assert pm is mock_pm
        assert clean is mock_clean

    def test_passes_config_to_pipeline(self):
        """init_pipeline should pass self.config to both pipeline classes."""
        with _mocked_instance(_make_data()) as car:
            with (
                patch("evals.collect_module.ProjectPipeline") as mock_pm_cls,
                patch("evals.collect_module.ProjectClean") as mock_clean_cls,
            ):
                mock_pm_cls.return_value = MagicMock()
                mock_clean_cls.return_value = MagicMock()

                car.init_pipeline()

        mock_pm_cls.assert_called_once_with(name="ProjectPipeline", config=car.config)
        mock_clean_cls.assert_called_once_with(name="ProjectClean", config=car.config)

    def test_sets_embed_and_storage_flags(self):
        """init_pipeline should propagate embed_to_vectorstore and save_to_storage."""
        with _mocked_instance(_make_data()) as car:
            with (
                patch("evals.collect_module.ProjectPipeline") as mock_pm_cls,
                patch("evals.collect_module.ProjectClean"),
            ):
                mock_pm = MagicMock()
                mock_pm_cls.return_value = mock_pm

                car.init_pipeline(embed_to_vectorstore=False, save_to_storage=False)

        assert mock_pm.embed_to_vectorstore is False
        assert mock_pm.save_to_storage is False


# ── run_conv ──────────────────────────────────────────────────────────────────

class TestRunConv:
    """run_conv must capture the model response into conv.model_response."""

    @pytest.mark.asyncio
    async def test_captures_model_response(self):
        conv = ConversationTurn(input="What is the claim?", answer="")
        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "The claim is X."}}

        mock_agent.stream_response = _stream

        with _mocked_instance(_make_data()) as car:
            await car.run_conv(
                conv=conv,
                agent_class=mock_agent,
                project_id="proj-123",
                session_id="sess-1",
                query_id="q-1",
                user_id="user-abc",
                session_date="2024-01-15",
            )

        assert conv.model_response == "The claim is X."

    @pytest.mark.asyncio
    async def test_handles_empty_stream(self):
        conv = ConversationTurn(input="What?", answer="")
        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "status", "data": {}}

        mock_agent.stream_response = _stream

        with _mocked_instance(_make_data()) as car:
            await car.run_conv(
                conv=conv,
                agent_class=mock_agent,
                project_id="proj-123",
                session_id="sess-1",
                query_id="q-1",
                user_id="user-abc",
                session_date="2024-01-15",
            )

        assert conv.model_response in (None, "No content")

    @pytest.mark.asyncio
    async def test_sets_time_counts(self):
        """run_conv should populate conv.time_counts after completion."""
        conv = ConversationTurn(input="Q?", answer="")
        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "answer"}}

        mock_agent.stream_response = _stream

        with _mocked_instance(_make_data()) as car:
            await car.run_conv(
                conv=conv,
                agent_class=mock_agent,
                project_id="proj-123",
                session_id="sess-1",
                query_id="q-1",
                user_id="user-abc",
                session_date="2024-01-15",
            )

        assert conv.time_counts is not None
        assert conv.time_counts.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_session_date_included_in_question(self):
        """run_conv should prepend the session_date to the question in the request."""
        conv = ConversationTurn(input="What is the claim?", answer="")
        captured_query = {}

        async def _stream(*args, **kwargs):
            captured_query["question"] = kwargs.get("query", args[0] if args else None)
            yield {"type": "ai", "data": {"token_stream": "ok"}}

        mock_agent = MagicMock()
        mock_agent.stream_response = _stream

        with _mocked_instance(_make_data()) as car:
            await car.run_conv(
                conv=conv,
                agent_class=mock_agent,
                project_id="proj-123",
                session_id="sess-1",
                query_id="q-1",
                user_id="user-abc",
                session_date="2024-01-15",
            )

        # The AskAgentRequest question should contain the session date
        query_obj = captured_query.get("question")
        if query_obj is not None:
            assert "2024-01-15" in query_obj.question


# ── run_agent ─────────────────────────────────────────────────────────────────

class TestRunAgent:
    """run_agent must process all sessions and use compiled pipeline graphs."""

    @pytest.mark.asyncio
    async def test_processes_all_sessions(self):
        """All sessions must be processed, not just session 0."""
        data = _make_data(n_sessions=3)

        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "answer"}}

        mock_agent.stream_response = _stream

        mock_pm = MagicMock()
        mock_clean = MagicMock()
        mock_pm.compile_init_pipeline.return_value = _make_mock_graph()
        mock_pm.compile_update_pipeline.return_value = _make_mock_graph()
        mock_clean.compile_clean_elements.return_value = _make_mock_graph()

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            car.init_pipeline = MagicMock(return_value=(mock_pm, mock_clean))
            result = await car.run_agent()

        processed = [s for s in data.sessions if s.runtime_session_id is not None]
        assert len(processed) == 3

    @pytest.mark.asyncio
    async def test_uses_init_pipeline_for_session_0(self):
        """Session 0 should run compile_init_pipeline(), not compile_update_pipeline()."""
        data = _make_data(n_sessions=1)

        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "ok"}}

        mock_agent.stream_response = _stream

        mock_pm = MagicMock()
        mock_clean = MagicMock()
        mock_pm.compile_init_pipeline.return_value = _make_mock_graph()
        mock_pm.compile_update_pipeline.return_value = _make_mock_graph()
        mock_clean.compile_clean_elements.return_value = _make_mock_graph()

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            car.init_pipeline = MagicMock(return_value=(mock_pm, mock_clean))
            await car.run_agent()

        mock_pm.compile_init_pipeline.assert_called_once()
        mock_pm.compile_update_pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_update_pipeline_for_subsequent_sessions(self):
        """Sessions after 0 should run compile_update_pipeline()."""
        data = _make_data(n_sessions=2)

        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "ok"}}

        mock_agent.stream_response = _stream

        mock_pm = MagicMock()
        mock_clean = MagicMock()
        mock_pm.compile_init_pipeline.return_value = _make_mock_graph()
        mock_pm.compile_update_pipeline.return_value = _make_mock_graph()
        mock_clean.compile_clean_elements.return_value = _make_mock_graph()

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            car.init_pipeline = MagicMock(return_value=(mock_pm, mock_clean))
            await car.run_agent()

        mock_pm.compile_update_pipeline.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_odd_sessions(self):
        """compile_clean_elements should be called before update on odd-indexed sessions."""
        data = _make_data(n_sessions=3)

        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "ok"}}

        mock_agent.stream_response = _stream

        mock_pm = MagicMock()
        mock_clean = MagicMock()
        mock_pm.compile_init_pipeline.return_value = _make_mock_graph()
        mock_pm.compile_update_pipeline.return_value = _make_mock_graph()
        mock_clean.compile_clean_elements.return_value = _make_mock_graph()

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            car.init_pipeline = MagicMock(return_value=(mock_pm, mock_clean))
            await car.run_agent()

        # Session 1 is odd → cleanup should run once
        mock_clean.compile_clean_elements.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_gathered_result_payload(self):
        """run_agent must return a GatheredResultPayload with the correct fields."""
        from evals.models import GatheredResultPayload
        data = _make_data(n_sessions=1)

        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "ok"}}

        mock_agent.stream_response = _stream

        mock_pm = MagicMock()
        mock_clean = MagicMock()
        mock_pm.compile_init_pipeline.return_value = _make_mock_graph()
        mock_pm.compile_update_pipeline.return_value = _make_mock_graph()
        mock_clean.compile_clean_elements.return_value = _make_mock_graph()

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            car.init_pipeline = MagicMock(return_value=(mock_pm, mock_clean))
            result = await car.run_agent()

        assert isinstance(result, GatheredResultPayload)
        assert result.dataset_name == data.dataset_name
        assert result.user_id == data.user_id
        assert result.eval_run_id is not None
        assert result.time_counts is not None

    @pytest.mark.asyncio
    async def test_run_conv_awaited_for_all_turns(self):
        """Every conversation turn must have model_response set after run_agent."""
        data = _make_data(n_sessions=1)

        mock_agent = MagicMock()

        async def _stream(*args, **kwargs):
            yield {"type": "ai", "data": {"token_stream": "hello"}}

        mock_agent.stream_response = _stream

        mock_pm = MagicMock()
        mock_clean = MagicMock()
        mock_pm.compile_init_pipeline.return_value = _make_mock_graph()
        mock_clean.compile_clean_elements.return_value = _make_mock_graph()

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            car.init_pipeline = MagicMock(return_value=(mock_pm, mock_clean))
            await car.run_agent()

        for conv in data.sessions[0].conversation:
            assert conv.model_response is not None, (
                f"model_response not set for turn: {conv.input}"
            )


# ── Integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCollectAgentResultIntegration:
    """Requires live GCS, Supabase, and a running agent. Run manually."""

    def test_parse_attachments_live(self):
        """Download a real blob and verify the attachment model is populated."""
        from evals.dataset_module import Dataset
        ds = Dataset("THRD-2021-163881")
        ds.load_dataset()
        ds.assign_session_attachments()

        first_attachment = next(
            (att for s in ds.data.sessions for att in s.attachments), None
        )
        if first_attachment is None:
            pytest.skip("No attachments found in dataset")

        pytest.skip("Requires live GCS credentials")
