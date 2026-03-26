"""
Tests for rate limiting, retry logic, and parallel async execution.
"""
import asyncio
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, call
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.rate_limiters import InMemoryRateLimiter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.utils import pick_llm, apply_retry, _rate_limiters
from agent.pipelines import ProjectPipeline
from agent.clean import ProjectClean
from models import PipelineState, AskAgentRequest, AttachmentModel, FactSheet, CleanupElementsRequest
from tests.fixtures.agent_data import get_mock_ask_agent_request


# ============================================
#           HELPERS
# ============================================

def make_mock_config(
    llm_rps=None,
    llm_concurrent=5,
    llm_retry=0,
    db_concurrent=2,
    storage_concurrent=1,
    vs_concurrent=2,
):
    cfg = MagicMock()
    cfg.async_tasks.llm.requests_per_second = llm_rps
    cfg.async_tasks.llm.max_concurrent_requests = llm_concurrent
    cfg.async_tasks.llm.max_burst_size = 10
    cfg.async_tasks.llm.retry_attempts = llm_retry
    cfg.async_tasks.llm.throttle_value = 0
    cfg.async_tasks.database.max_concurrent_requests = db_concurrent
    cfg.async_tasks.storage.max_concurrent_requests = storage_concurrent
    cfg.async_tasks.vectorstore.max_concurrent_requests = vs_concurrent
    cfg.models.together.base_url = "https://api.together.xyz/v1"
    cfg.models.together.max_tokens = 4096
    return cfg


# ============================================
#           pick_llm — RATE LIMITER
# ============================================

class TestPickLlmRateLimiter:

    def setup_method(self):
        _rate_limiters.clear()

    def test_no_rate_limiter_when_rps_is_none(self):
        cfg = make_mock_config(llm_rps=None)
        with patch('agent.utils.init_chat_model') as mock_init:
            mock_llm = MagicMock()
            mock_init.return_value = mock_llm
            pick_llm("google_gemini-2.5-flash", cfg)
            _, kwargs = mock_init.call_args
            assert kwargs.get("rate_limiter") is None

    def test_rate_limiter_created_when_rps_set(self):
        cfg = make_mock_config(llm_rps=0.5)
        with patch('agent.utils.init_chat_model') as mock_init:
            mock_llm = MagicMock()
            mock_init.return_value = mock_llm
            pick_llm("google_gemini-2.5-flash", cfg)
            _, kwargs = mock_init.call_args
            assert isinstance(kwargs.get("rate_limiter"), InMemoryRateLimiter)

    def test_rate_limiter_is_cached_per_model(self):
        cfg = make_mock_config(llm_rps=0.5)
        with patch('agent.utils.init_chat_model') as mock_init:
            mock_init.return_value = MagicMock()
            pick_llm("google_gemini-2.5-flash", cfg)
            pick_llm("google_gemini-2.5-flash", cfg)
            # Same rate limiter instance used both times
            calls = mock_init.call_args_list
            rl1 = calls[0][1].get("rate_limiter")
            rl2 = calls[1][1].get("rate_limiter")
            assert rl1 is rl2

    def test_different_models_get_different_rate_limiters(self):
        cfg = make_mock_config(llm_rps=0.5)
        with patch('agent.utils.init_chat_model') as mock_init:
            mock_init.return_value = MagicMock()
            pick_llm("google_gemini-2.5-flash", cfg)
            pick_llm("openai_gpt-4o-mini", cfg)
            calls = mock_init.call_args_list
            rl1 = calls[0][1].get("rate_limiter")
            rl2 = calls[1][1].get("rate_limiter")
            assert rl1 is not rl2


# ============================================
#           apply_retry
# ============================================

class TestApplyRetry:

    def test_no_retry_when_attempts_zero(self):
        cfg = make_mock_config(llm_retry=0)
        mock_llm = MagicMock()
        result = apply_retry(mock_llm, cfg)
        assert result is mock_llm

    def test_retry_applied_when_attempts_nonzero(self):
        cfg = make_mock_config(llm_retry=3)
        mock_llm = MagicMock()
        mock_with_retry = MagicMock()
        mock_llm.with_retry.return_value = mock_with_retry
        result = apply_retry(mock_llm, cfg)
        mock_llm.with_retry.assert_called_once_with(stop_after_attempt=3, wait_exponential_jitter=True)
        assert result is mock_with_retry

    def test_retry_wraps_chain_not_base_llm(self):
        """Retry must be applied after bind_tools/with_structured_output, not before."""
        cfg = make_mock_config(llm_retry=6)
        mock_chain = MagicMock()
        mock_chain.with_retry.return_value = MagicMock()
        apply_retry(mock_chain, cfg)
        mock_chain.with_retry.assert_called_once()


# ============================================
#           429 RETRY BEHAVIOUR
# ============================================

class TestCallLlmRetry:

    def test_call_llm_retry_applied_after_bind_tools(self):
        """apply_retry must be called on the bind_tools result, not on the base llm."""
        cfg = make_mock_config(llm_retry=3)

        mock_llm = MagicMock()
        mock_bound = MagicMock()
        mock_retried = MagicMock()
        mock_llm.bind_tools.return_value = mock_bound
        mock_bound.with_retry.return_value = mock_retried

        with patch('agent.utils.init_chat_model', return_value=mock_llm):
            base = pick_llm("google_gemini-2.5-flash", cfg)
            # Simulate what _compile_agent does
            chain = apply_retry(base.bind_tools([]), cfg)

        mock_bound.with_retry.assert_called_once_with(stop_after_attempt=3, wait_exponential_jitter=True)
        assert chain is mock_retried

    @pytest.mark.asyncio
    async def test_llm_raises_after_max_retries(self):
        """After exhausting retry attempts, the exception should propagate."""
        call_count = 0

        async def failing_ainvoke(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("429 Too Many Requests")

        mock_chain = AsyncMock()
        mock_chain.ainvoke.side_effect = failing_ainvoke

        cfg = make_mock_config(llm_retry=0)  # no retry — fails immediately
        mock_chain_with_retry = mock_chain

        with pytest.raises(Exception, match="429"):
            await mock_chain_with_retry.ainvoke("test")

        assert call_count == 1  # no retry, fails once


# ============================================
#           PARALLEL PARSING NODE
# ============================================

@pytest.fixture
async def mock_pipeline():
    with patch('agent.pipelines.ContextManager'), \
         patch('agent.pipelines.DocumentProcessor') as mock_dp, \
         patch('agent.pipelines.GCSManager'), \
         patch('agent.pipelines.BQVectorStore') as mock_bq, \
         patch('agent.pipelines.SupabaseManager'):

        mock_dp_instance = MagicMock()
        mock_dp.return_value = mock_dp_instance
        mock_bq_instance = MagicMock()
        mock_bq_instance.embedding_model = "mock-model"
        mock_bq.return_value = mock_bq_instance

        cfg = make_mock_config()
        cfg.project.embed_to_vectorstore = True
        cfg.project.save_to_storage = True
        cfg.storage.aws.region = "eu-west-1"
        cfg.storage.aws.bucket_name = "test-bucket"

        pipeline = ProjectPipeline(name="test", config=cfg)
        pipeline.document_processor = mock_dp_instance
        pipeline.vs = mock_bq_instance
        yield pipeline


@pytest.mark.asyncio
async def test_parsing_node_processes_attachments_in_parallel(mock_pipeline):
    """All attachments should be parsed concurrently, not sequentially."""
    import base64

    parse_start_times = []

    def slow_parse(*args, **kwargs):
        import time
        parse_start_times.append(time.monotonic())
        return [MagicMock(metadata={"file_id": kwargs.get("metadata", {}).get("file_id", "unknown")})]

    mock_pipeline.document_processor.parse_to_docs.side_effect = slow_parse
    mock_pipeline.document_processor.to_plain_text.return_value = "body text"

    attachments = [
        AttachmentModel(
            file_id=f"file-{i}",
            filename=f"doc{i}.txt",
            file_type="text/plain",
            content=base64.b64encode(b"content").decode(),
            path=f"user/session/file-{i}.txt",
            size=7,
            query_id="q1",
        )
        for i in range(3)
    ]

    query = get_mock_ask_agent_request()
    query.attachments = attachments
    state = PipelineState(query=query)

    with patch('agent.pipelines.get_config', return_value={"configurable": {"user_id": "u1"}}), \
         patch('agent.pipelines.get_stream_writer', return_value=lambda x: None), \
         patch('agent.pipelines.PDFHandler'):
        result = await mock_pipeline._parsing_node(state)

    assert len(result["docs_by_file"]) == 3
    assert mock_pipeline.document_processor.parse_to_docs.call_count == 3


@pytest.mark.asyncio
async def test_parsing_node_skips_filtered_emails(mock_pipeline):
    """EML attachments not in shortened_email_ids should be skipped."""
    import base64

    mock_pipeline.document_processor.parse_to_docs.return_value = [
        MagicMock(metadata={"file_id": "eml-1"})
    ]
    mock_pipeline.document_processor.to_plain_text.return_value = ""

    eml_att = AttachmentModel(
        file_id="eml-1",
        filename="email.eml",
        file_type="message/rfc822",
        content=base64.b64encode(b"eml content").decode(),
        path="user/session/eml-1.eml",
        size=11,
        query_id="q1",
    )
    query = get_mock_ask_agent_request()
    query.attachments = [eml_att]
    state = PipelineState(query=query, collapsed_emails={"other-id": MagicMock()})

    with patch('agent.pipelines.get_config', return_value={"configurable": {"user_id": "u1"}}), \
         patch('agent.pipelines.get_stream_writer', return_value=lambda x: None), \
         patch('agent.pipelines.PDFHandler'):
        result = await mock_pipeline._parsing_node(state)

    mock_pipeline.document_processor.parse_to_docs.assert_not_called()
    assert result["docs_by_file"] == {}


# ============================================
#           PARALLEL SAVE NODE
# ============================================

@pytest.fixture
async def mock_clean():
    with patch('agent.clean.ContextManager'), \
         patch('agent.clean.DocumentProcessor'), \
         patch('agent.clean.GCSManager'), \
         patch('agent.clean.BQVectorStore'), \
         patch('agent.clean.SupabaseManager') as mock_db:

        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        cfg = make_mock_config()
        cfg.project.clean.chunk_size = 50

        clean = ProjectClean(name="test-cleaner", config=cfg)
        clean.conversation_manager = mock_db_instance
        yield clean


@pytest.mark.asyncio
async def test_save_elements_node_parallel(mock_clean):
    """DB upserts for different element types should run in parallel."""
    mock_clean.conversation_manager.upsert_replace_project_element = MagicMock()

    base = get_mock_ask_agent_request()
    query = CleanupElementsRequest(**base.model_dump(), element_types=["events", "claims"])

    mock_factsheet = MagicMock()
    mock_factsheet.model_dump.return_value = {
        "events": [{"description": "e1"}],
        "claims": [{"description": "c1"}],
    }
    mock_project_data = MagicMock()
    mock_project_data.factsheet = mock_factsheet
    state = PipelineState(query=query)
    state.input_ = mock_project_data

    with patch('agent.clean.get_stream_writer', return_value=lambda x: None), \
         patch('agent.clean.get_config', return_value={"configurable": {"user_id": "u1"}}):
        await mock_clean._save_elements_node(state)

    assert mock_clean.conversation_manager.upsert_replace_project_element.call_count == 2
    called_tables = {
        c.kwargs["table_name"]
        for c in mock_clean.conversation_manager.upsert_replace_project_element.call_args_list
    }
    assert called_tables == {"project_events", "project_claims"}


# ============================================
#           CONTEXT MANAGER _structured
# ============================================

class TestContextManagerStructured:

    def test_structured_returns_chain_without_retry_when_disabled(self):
        from agent.context_manager import ContextManager
        cfg = make_mock_config(llm_retry=0)
        mock_llm = MagicMock()
        mock_chain = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain

        cm = ContextManager(llm=mock_llm, config=cfg)
        result = cm._structured(MagicMock())

        assert result is mock_chain
        mock_chain.with_retry.assert_not_called()

    def test_structured_applies_retry_after_chain(self):
        from agent.context_manager import ContextManager
        cfg = make_mock_config(llm_retry=4)
        mock_llm = MagicMock()
        mock_chain = MagicMock()
        mock_retried = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain
        mock_chain.with_retry.return_value = mock_retried

        cm = ContextManager(llm=mock_llm, config=cfg)
        result = cm._structured(MagicMock())

        mock_chain.with_retry.assert_called_once_with(stop_after_attempt=4, wait_exponential_jitter=True)
        assert result is mock_retried
