import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, AIMessageChunk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.agent import Agent
from agent.utils import pick_llm
from models import AgentState
from models import *
from tests.fixtures.agent_data import (
    get_mock_ask_agent_request,
    get_mock_ask_agent_request_with_attachments,
    get_mock_ai_message,
    get_mock_ai_message_with_tool_calls,
    get_mock_initial_input,
    get_mock_analyzed_doc,
    get_mock_vector_store_docs
)


@pytest.fixture
def mock_agent():
    """Creates an Agent with mocked dependencies."""
    with patch('agent.agent.ChromaVectorStore') as mock_chroma, \
         patch('agent.agent.BQVectorStore') as mock_bq, \
         patch('agent.agent.DocumentProcessor') as mock_doc_processor, \
         patch('agent.agent.Summarizer') as mock_summarizer, \
         patch('agent.agent.SupabaseStorageManager') as mock_storage, \
         patch('agent.agent.SupabaseManager') as mock_conversation_manager, \
         patch('agent.agent.ContextManager') as mock_context_manager, \
         patch('agent.agent.ToolManager') as mock_tool_manager, \
         patch.object(Agent, 'load_prompt', return_value="Mock system prompt"):

        mock_chroma_instance = MagicMock()
        mock_chroma.return_value = mock_chroma_instance

        mock_bq_instance = MagicMock()
        mock_bq.return_value = mock_bq_instance

        mock_doc_processor_instance = MagicMock()
        mock_doc_processor.return_value = mock_doc_processor_instance

        mock_summarizer_instance = MagicMock()
        mock_summarizer.return_value = mock_summarizer_instance

        mock_storage_instance = MagicMock()
        mock_storage.return_value = mock_storage_instance

        mock_conversation_manager_instance = MagicMock()
        mock_conversation_manager.return_value = mock_conversation_manager_instance

        mock_context_manager_instance = MagicMock()
        mock_context_manager.return_value = mock_context_manager_instance

        mock_tool_manager_instance = MagicMock()
        mock_tool_manager.return_value = mock_tool_manager_instance

        mock_config = MagicMock()
        mock_config.async_tasks.llm.max_concurrent_requests = 3
        mock_config.async_tasks.llm.throttle_value = 0
        mock_config.async_tasks.llm.requests_per_second = None
        mock_config.async_tasks.llm.retry_attempts = 0
        mock_config.async_tasks.database.max_concurrent_requests = 2
        mock_config.async_tasks.storage.max_concurrent_requests = 1
        mock_config.async_tasks.vectorstore.max_concurrent_requests = 2
        mock_config.agent.max_token_tool = 10000
        mock_config.agent.context_window = 128000
        mock_config.agent.sum_rate = 20
        mock_config.agent.use_factsheet = False
        mock_config.agent.minimal_context = False
        mock_config.agent.significance = ["high", "medium", "low"]
        mock_config.agent.embed_to_vectorstore = False
        mock_config.agent.save_to_storage = False

        agent = Agent(
            tools=[],
            config=mock_config,
        )

        agent.in_memory_store = mock_chroma_instance
        agent.vs = mock_bq_instance
        agent.document_processor = mock_doc_processor_instance
        agent.summarizer = mock_summarizer_instance
        agent.storage = mock_storage_instance
        agent.conversation_manager = mock_conversation_manager_instance
        agent.context_manager = mock_context_manager_instance
        agent.tool_manager = mock_tool_manager_instance

        yield agent


# ============================================
#           SANITIZE PAYLOAD TESTS
# ============================================

def test_sanitize_payload_valid_sequence_unchanged(mock_agent):
    """A valid payload should pass through unchanged."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 3
    assert isinstance(result[0], SystemMessage)
    assert isinstance(result[1], HumanMessage)
    assert isinstance(result[2], AIMessage)


def test_sanitize_payload_merges_consecutive_human_messages(mock_agent):
    """Consecutive HumanMessages should be merged."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Factsheet context"),
        HumanMessage(content="User question"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 2
    assert isinstance(result[1], HumanMessage)
    assert "Factsheet context" in result[1].content
    assert "User question" in result[1].content


def test_sanitize_payload_merges_consecutive_ai_messages(mock_agent):
    """Consecutive AIMessages should be merged."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content="Summary of conversation"),
        AIMessage(content="Actual response"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 3
    assert isinstance(result[2], AIMessage)
    assert "Summary" in result[2].content
    assert "Actual response" in result[2].content


def test_sanitize_payload_normalizes_ai_list_content(mock_agent):
    """AIMessage with list content should be normalized to string."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content=[{"type": "text", "text": "Hello "}, {"type": "text", "text": "World"}]),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert isinstance(result[2], AIMessage)
    assert isinstance(result[2].content, str)
    assert result[2].content == "Hello World"


def test_sanitize_payload_strips_orphan_tool_calls(mock_agent):
    """AIMessage with tool_calls but no following ToolMessage should have tool_calls stripped."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content="Let me check", tool_calls=[{"name": "search", "args": {}, "id": "tc1"}]),
        HumanMessage(content="Q2"),
        AIMessage(content="A2"),
    ]
    result = mock_agent._sanitize_payload(payload)
    ai_msgs = [m for m in result if isinstance(m, AIMessage)]
    for ai in ai_msgs:
        if "check" in (ai.content or ""):
            assert not ai.tool_calls


def test_sanitize_payload_keeps_valid_tool_call_sequence(mock_agent):
    """AIMessage with tool_calls followed by ToolMessage should be preserved."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content="Let me search", tool_calls=[{"name": "search", "args": {}, "id": "tc1"}]),
        ToolMessage(content="search result", tool_call_id="tc1", name="search"),
        AIMessage(content="Based on the search..."),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 5
    assert result[2].tool_calls


def test_sanitize_payload_empty(mock_agent):
    """Empty payload should return empty."""
    result = mock_agent._sanitize_payload([])
    assert result == []


def test_sanitize_payload_full_conversation_with_tools(mock_agent):
    """Full multi-turn conversation with tool calls should remain valid."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content="A1", tool_calls=[{"name": "t1", "args": {}, "id": "tc1"}]),
        ToolMessage(content="R1", tool_call_id="tc1", name="t1"),
        AIMessage(content="Final A1"),
        HumanMessage(content="Q2"),
        AIMessage(content="A2"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 7
    types = [type(m).__name__ for m in result]
    assert types == ["SystemMessage", "HumanMessage", "AIMessage", "ToolMessage", "AIMessage", "HumanMessage", "AIMessage"]


def test_sanitize_payload_three_consecutive_human_messages(mock_agent):
    """Three consecutive HumanMessages should all be merged into one."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Part 1"),
        HumanMessage(content="Part 2"),
        HumanMessage(content="Part 3"),
        AIMessage(content="Response"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 3
    human = result[1]
    assert "Part 1" in human.content
    assert "Part 2" in human.content
    assert "Part 3" in human.content


# ============================================
#           HELPER FUNCTION TESTS
# ============================================

def test_build_attachment_context_empty(mock_agent):
    """Test _build_attachment_context with empty inputs."""
    result = mock_agent._build_attachment_context(
        attachments=[],
        attachment_contents={},
        user_input="Test query"
    )
    assert result == ""


def test_build_attachment_context_with_attachments(mock_agent):
    """Test _build_attachment_context with attachments and content."""
    attachments = [
        {"file_id": "file-001", "filename": "test.pdf", "path": "path/to/test.pdf"},
        {"file_id": "file-002", "filename": "test2.txt", "path": "path/to/test2.txt"}
    ]
    attachment_contents = {
        "file-001": "Content of file 001",
        "file-002": "Content of file 002"
    }

    result = mock_agent._build_attachment_context(
        attachments=attachments,
        attachment_contents=attachment_contents,
        user_input="Test query"
    )

    assert "User's documents" in result
    assert "Content of file 001" in result
    assert "Content of file 002" in result
    assert "test.pdf" in result


def test_should_continue_with_tool_calls(mock_agent):
    """Test _should_continue returns True when there are tool calls."""
    ai_msg = get_mock_ai_message_with_tool_calls()
    state = AgentState(messages=[ai_msg])

    result = mock_agent._should_continue(state)
    assert result is True


def test_should_continue_without_tool_calls(mock_agent):
    """Test _should_continue returns False when there are no tool calls."""
    ai_msg = get_mock_ai_message()
    state = AgentState(messages=[ai_msg])

    result = mock_agent._should_continue(state)
    assert result is False


# ============================================
#           CALL LLM TESTS
# ============================================

@pytest.mark.asyncio
async def test_call_llm_basic(mock_agent):
    """Test _call_llm basic invocation."""
    state = AgentState(messages=[
        SystemMessage(content="System prompt"),
        HumanMessage(
            content="Test question",
            additional_kwargs={
                "query_id": "query-001",
                "session_id": "session-001",
                "attachments": []
            }
        )
    ])

    ai_chunk = AIMessageChunk(content="Test response", id="ai-001")

    async def mock_astream(*args, **kwargs):
        yield ai_chunk

    mock_llm = MagicMock()
    mock_llm.astream = mock_astream
    mock_agent.llm = mock_llm
    mock_agent.conversation_manager.load_project.return_value = None

    mock_config = {
        "configurable": {"custom_project_id": None, "query_id": "query-001"},
        "metadata": {"query_id": "query-001"}
    }

    with patch('agent.agent.get_config', return_value=mock_config):
        result = await mock_agent._call_llm(state)

    assert "messages" in result
    assert len(result["messages"]) >= 1


@pytest.mark.asyncio
async def test_call_llm_with_project_data(mock_agent):
    """Test _call_llm includes factsheet when project data exists."""
    from tests.fixtures.context_manager_data import get_mock_factsheet

    state = AgentState(messages=[
        SystemMessage(content="System prompt"),
        HumanMessage(
            content="Test question",
            additional_kwargs={
                "query_id": "query-001",
                "session_id": "session-001",
                "attachments": []
            }
        )
    ])

    ai_chunk = AIMessageChunk(content="Test response", id="ai-002")

    async def mock_astream(*args, **kwargs):
        yield ai_chunk

    mock_llm = MagicMock()
    mock_llm.astream = mock_astream
    mock_agent.llm = mock_llm

    mock_project = ProjectData(factsheet=get_mock_factsheet(), attachments=[], emails=[])
    mock_agent.conversation_manager.load_project.return_value = mock_project

    mock_config = {
        "configurable": {"custom_project_id": "project-001", "query_id": "query-001"},
        "metadata": {"query_id": "query-001"}
    }

    with patch('agent.agent.get_config', return_value=mock_config):
        result = await mock_agent._call_llm(state)

    assert "messages" in result


@pytest.mark.asyncio
async def test_call_llm_with_attachments(mock_agent):
    """Test _call_llm builds attachment context from message kwargs."""
    attachments = [{"file_id": "file-001", "filename": "test.pdf", "body": "Document content", "path": "path/to/file"}]
    state = AgentState(messages=[
        SystemMessage(content="System prompt"),
        HumanMessage(
            content="Test question",
            additional_kwargs={
                "query_id": "query-001",
                "session_id": "session-001",
                "attachments": attachments
            }
        )
    ])

    ai_chunk = AIMessageChunk(content="Test response", id="ai-003")

    async def mock_astream(*args, **kwargs):
        yield ai_chunk

    mock_llm = MagicMock()
    mock_llm.astream = mock_astream
    mock_agent.llm = mock_llm
    mock_agent.conversation_manager.load_project.return_value = None

    mock_config = {
        "configurable": {"custom_project_id": None, "query_id": "query-001"},
        "metadata": {"query_id": "query-001"}
    }

    with patch('agent.agent.get_config', return_value=mock_config):
        result = await mock_agent._call_llm(state)

    assert "messages" in result


# ============================================
#           CALL TOOL TESTS
# ============================================

@pytest.mark.asyncio
async def test_call_tool_no_tool_calls(mock_agent):
    """Test _call_tool with no tool calls returns empty messages."""
    ai_msg = get_mock_ai_message()
    state = AgentState(messages=[ai_msg])

    mock_config = {"configurable": {}, "metadata": {"query_id": "query-001"}}
    with patch('agent.agent.get_config', return_value=mock_config):
        result = await mock_agent._call_tool(state)

    assert result["messages"] == []


@pytest.mark.asyncio
async def test_call_tool_with_tool_calls(mock_agent):
    """Test _call_tool executes tool and returns ToolMessage result."""
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.ainvoke = AsyncMock(return_value="Tool result")

    mock_agent.tools = [mock_tool]
    mock_agent.tool_manager.format_tool_result.return_value = "Formatted result"

    ai_msg = AIMessage(
        content="",
        id="ai-001",
        tool_calls=[{"name": "test_tool", "args": {"arg1": "value1"}, "id": "tool-call-001"}]
    )
    state = AgentState(messages=[ai_msg])

    mock_config = {"configurable": {}, "metadata": {"query_id": "query-001"}}
    with patch('agent.agent.get_config', return_value=mock_config):
        result = await mock_agent._call_tool(state)

    mock_tool.ainvoke.assert_called_once()
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)


@pytest.mark.asyncio
async def test_call_tool_invalid_tool_name(mock_agent):
    """Test _call_tool handles invalid tool name gracefully."""
    mock_agent.tools = []

    ai_msg = AIMessage(
        content="",
        id="ai-001",
        tool_calls=[{"name": "nonexistent_tool", "args": {}, "id": "tool-call-001"}]
    )
    state = AgentState(messages=[ai_msg])

    mock_config = {"configurable": {}, "metadata": {"query_id": "query-001"}}
    with patch('agent.agent.get_config', return_value=mock_config):
        result = await mock_agent._call_tool(state)

    assert len(result["messages"]) == 1
    assert "Incorrect Tool Name" in result["messages"][0].content


# ============================================
#           STREAM EVENT HANDLERS
# ============================================

def test_on_chat_model_stream(mock_agent):
    """Test on_chat_model_stream extracts token from chunk."""
    chunk = AIMessageChunk(content="Hello")
    data = {"chunk": chunk}

    result = mock_agent.on_chat_model_stream(data, query_id="query-001", token_stream="")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["type"] == "token"
    assert result[0]["data"] == "Hello"
    assert result[0]["query_id"] == "query-001"


def test_on_chat_model_stream_no_chunk(mock_agent):
    """Test on_chat_model_stream returns empty list when no chunk."""
    data = {"chunk": None}

    result = mock_agent.on_chat_model_stream(data, query_id="query-001", token_stream="")

    assert result == []


def test_on_call_llm(mock_agent):
    """Test on_call_llm creates stream event from AI message."""
    ai_msg = get_mock_ai_message()
    data = {"output": {"messages": [ai_msg]}}
    events = []

    result = mock_agent.on_call_llm(
        data,
        query_id="query-001",
        session_id="session-001",
        events=events,
        event_counter=0,
        token_stream="Hello world"
    )

    assert result is not None
    assert result["type"] == "ai"
    assert len(events) == 1


def test_on_call_llm_no_output(mock_agent):
    """Test on_call_llm returns None when no output."""
    data = {"output": None}
    events = []

    result = mock_agent.on_call_llm(
        data,
        query_id="query-001",
        session_id="session-001",
        events=events,
        event_counter=0,
        token_stream=""
    )

    assert result is None


# ============================================
#           COMPILE AGENT TEST
# ============================================

def test_compile_agent(mock_agent):
    """Test _compile_agent creates a runnable graph."""
    with patch('agent.agent.pick_llm') as mock_pick_llm:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_pick_llm.return_value = mock_llm

        agent_instance = mock_agent._compile_agent(llm_model="google_gemini-2.5-flash")

        assert hasattr(agent_instance, 'astream_events')
        mock_llm.bind_tools.assert_called_once()


# ============================================
#           PICK LLM TESTS (standalone function)
# ============================================

def test_pick_llm_google():
    """Test pick_llm with google provider."""
    cfg = MagicMock()
    cfg.async_tasks.llm.requests_per_second = None
    with patch('agent.utils.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()
        pick_llm("google_gemini-2.5-flash", config=cfg)
        args, kwargs = mock_init.call_args
        assert args == ("gemini-2.5-flash",)
        assert kwargs["model_provider"] == "google_genai"
        assert kwargs["include_thoughts"] is False
        assert kwargs["rate_limiter"] is None


def test_pick_llm_openai():
    """Test pick_llm with openai provider."""
    cfg = MagicMock()
    cfg.async_tasks.llm.requests_per_second = None
    with patch('agent.utils.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()
        pick_llm("openai_gpt-4o", config=cfg)
        args, kwargs = mock_init.call_args
        assert args == ("gpt-4o",)
        assert kwargs["model_provider"] == "openai"


def test_pick_llm_unknown_provider():
    """Test pick_llm with unknown provider defaults to google_genai."""
    cfg = MagicMock()
    cfg.async_tasks.llm.requests_per_second = None
    with patch('agent.utils.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()
        pick_llm("unknown_some-model", config=cfg)
        _, kwargs = mock_init.call_args
        assert kwargs["model_provider"] == "google_genai"
