"""Tests for CollectAgentResult.

NOTE: CollectAgentResult currently lives in eval.ipynb. Extract it to
evals/src/evals/collect_agent_result.py and adjust the import below before
running these tests.

Known bugs in the current notebook implementation — these tests document
and catch them:
  1. `if idx < 1` in run_agent → only session 0 is ever processed
  2. `run_conv(...)` is async but called without `await` → response silently lost
  3. `data.get("user_id")` uses the global `data` instead of `self.data`
"""
import pytest
import uuid
from base64 import b64encode
from unittest.mock import AsyncMock, MagicMock, patch, call

# from evals.collect_agent_result import CollectAgentResult  # uncomment after extraction


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_session(idx: int, date: str = "2024-01-15") -> dict:
    return {
        "session": idx,
        "session_id": str(uuid.uuid4()),
        "session_name": f"Session {idx}",
        "date": date,
        "init_query": f"Init query {idx}",
        "attachments": [],
        "conversation": [
            {"input": f"Query {idx}.1", "answer": "", "query_id": str(uuid.uuid4()), "order": 1},
            {"input": f"Query {idx}.2", "answer": "", "query_id": str(uuid.uuid4()), "order": 2},
        ],
    }


def _make_data(n_sessions: int = 2) -> dict:
    return {
        "dataset_name": "THRD-2021-163881",
        "project_id": "proj-123",
        "user_id": "user-abc",
        "llm_model": None,
        "sessions": [_make_session(i) for i in range(n_sessions)],
    }


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
        # Instantiate with a minimal mock so no real GCS calls happen
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


# ── run_conv ──────────────────────────────────────────────────────────────────

class TestRunConv:
    """run_conv must capture the model response into conv['model_response']."""

    @pytest.mark.asyncio
    async def test_captures_model_response(self):
        conv = {"input": "What is the claim?", "answer": ""}
        mock_agent = MagicMock()
        mock_agent.stream_response = AsyncMock(return_value=_async_gen([
            {"type": "ai", "data": {"token_stream": "The claim is X."}},
        ]))

        with _mocked_instance(_make_data()) as car:
            await car.run_conv(
                conv=conv,
                agent_class=mock_agent,
                project_id="proj-123",
                session_id="sess-1",
                query_id="q-1",
                user_id="user-abc",
            )

        assert conv["model_response"] == "The claim is X."

    @pytest.mark.asyncio
    async def test_handles_empty_stream(self):
        conv = {"input": "What?", "answer": ""}
        mock_agent = MagicMock()
        mock_agent.stream_response = AsyncMock(return_value=_async_gen([
            {"type": "status", "data": {}},
        ]))

        with _mocked_instance(_make_data()) as car:
            await car.run_conv(
                conv=conv,
                agent_class=mock_agent,
                project_id="proj-123",
                session_id="sess-1",
                query_id="q-1",
                user_id="user-abc",
            )
        # No "ai" chunk → model_response should not be set (or be "No content")
        assert conv.get("model_response") in (None, "No content")


# ── run_agent ─────────────────────────────────────────────────────────────────

class TestRunAgent:
    """Document the known bugs and desired correct behaviour."""

    @pytest.mark.asyncio
    async def test_processes_all_sessions(self):
        """BUG: `if idx < 1` means only session 0 runs. All sessions must be processed."""
        data = _make_data(n_sessions=3)

        mock_agent = MagicMock()
        mock_agent.initialize_project = AsyncMock(return_value=_async_gen([]))
        mock_agent.update_project = AsyncMock(return_value=_async_gen([]))
        mock_agent.stream_response = AsyncMock(return_value=_async_gen([
            {"type": "ai", "data": {"token_stream": "answer"}},
        ]))

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            await car.run_agent(session=None)

        # After the fix, all 3 sessions should have had their conversations run
        processed = [
            s for s in data["sessions"]
            if any("model_response" in c for c in s["conversation"])
        ]
        assert len(processed) == 3, (
            "Only session 0 was processed — `if idx < 1` bug still present"
        )

    @pytest.mark.asyncio
    async def test_uses_self_data_not_global(self):
        """BUG: run_agent references global `data` for user_id instead of self.data."""
        data = _make_data(n_sessions=1)
        data["user_id"] = "correct-user"

        mock_agent = MagicMock()
        mock_agent.initialize_project = AsyncMock(return_value=_async_gen([]))
        mock_agent.stream_response = AsyncMock(return_value=_async_gen([
            {"type": "ai", "data": {"token_stream": "ok"}},
        ]))

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            # If the global `data` bug exists, this will use whatever `data` is in
            # the module scope rather than car.data["user_id"] = "correct-user"
            await car.run_agent(session=None)

        init_call = mock_agent.initialize_project.call_args
        assert init_call.kwargs.get("user_id") == "correct-user"

    @pytest.mark.asyncio
    async def test_run_conv_is_awaited(self):
        """BUG: run_conv is async but called without await — response is lost."""
        data = _make_data(n_sessions=1)
        mock_agent = MagicMock()
        mock_agent.initialize_project = AsyncMock(return_value=_async_gen([]))
        mock_agent.stream_response = AsyncMock(return_value=_async_gen([
            {"type": "ai", "data": {"token_stream": "hello"}},
        ]))

        with _mocked_instance(data) as car:
            car.init_agent = AsyncMock(return_value=mock_agent)
            await car.run_agent(session=None)

        # If run_conv is properly awaited, model_response must be set on each conv
        for conv in data["sessions"][0]["conversation"]:
            assert "model_response" in conv, (
                "run_conv not awaited — model_response never written"
            )


# ── Integration tests ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCollectAgentResultIntegration:
    """Requires live GCS, Supabase, and a running agent. Run manually."""

    def test_parse_attachments_live(self):
        """Download a real blob and verify the attachment model is populated."""
        from evals.dataset import Dataset
        ds = Dataset("THRD-2021-163881")
        ds.load_dataset()
        ds.assign_session_attachments()

        first_attachment = next(
            (att for s in ds.data["sessions"] for att in s.get("attachments", [])), None
        )
        if first_attachment is None:
            pytest.skip("No attachments found in dataset")

        # Build a minimal CollectAgentResult to test parse_attachments
        # from evals.collect_agent_result import CollectAgentResult
        # car = CollectAgentResult(ds.data)
        # result = car.parse_attachments(first_attachment, "q-1", "sess-1", "user-1")
        # assert result.content  # base64 content must be non-empty
        pytest.skip("Uncomment after extracting CollectAgentResult to a module")


# ── Private helpers ───────────────────────────────────────────────────────────

from contextlib import contextmanager


@contextmanager
def _mocked_instance(data: dict):
    """Yield a CollectAgentResult with all GCS calls mocked out."""
    mock_bucket = MagicMock()
    mock_client = MagicMock()
    mock_client.bucket.return_value = mock_bucket

    # Patch both storage.Client (used inside Dataset.__init__) and
    # the Agent / checkpointer imports used in CollectAgentResult.
    with (
        patch("google.cloud.storage.Client", return_value=mock_client),
        patch("psycopg_pool.AsyncConnectionPool", MagicMock()),
        patch("langgraph.checkpoint.postgres.aio.AsyncPostgresSaver", MagicMock()),
    ):
        # from evals.collect_agent_result import CollectAgentResult
        # yield CollectAgentResult(data)

        # ── TEMPORARY: inline minimal stub until class is extracted ──────────
        from evals.dataset import Dataset
        from types import SimpleNamespace

        class _Stub:
            def __init__(self, d):
                self.data = d
                self.llm_model = "google_gemini-2.5-pro"
                self.dataclass = Dataset(name=d.get("dataset_name"), client=mock_client)

            def file_type_map(self, path):
                mapping = {
                    "txt": "text/plain",
                    "pdf": "application/pdf",
                    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "csv": "text/csv",
                    "md": "text/markdown",
                    "eml": "message/rfc822",
                }
                return mapping.get(path.rsplit(".", 1)[-1], None)

            def parse_attachments(self, attachment_path, query_id, session_id, user_id):
                from base64 import b64encode
                from agent.src.agent.basemodels import AttachmentModel
                raw = self.dataclass.bucket.blob(attachment_path).download_as_bytes()
                content = b64encode(raw).decode("utf-8")
                file_id = str(uuid.uuid4())
                return AttachmentModel(
                    filename=attachment_path,
                    file_type=self.file_type_map(attachment_path),
                    content=content,
                    file_id=file_id,
                    path=f"{user_id}/{session_id}/{file_id}.{attachment_path.rsplit('.', 1)[-1]}",
                    size=len(content),
                    query_id=query_id,
                )

            async def run_conv(self, conv, agent_class, project_id, session_id, query_id, user_id):
                from agent.src.agent.basemodels import AskAgentRequest
                input_obj = AskAgentRequest(
                    question=conv.get("input"),
                    session_id=session_id,
                    llm_model=self.llm_model,
                    query_id=query_id,
                    project_id=project_id,
                    attachments=[],
                )
                async for response in agent_class.stream_response(query=input_obj, user_id=user_id):
                    if response.get("type") == "ai":
                        conv["model_response"] = response.get("data", {}).get("token_stream", "No content")

        yield _Stub(data)


async def _async_gen(items):
    for item in items:
        yield item
