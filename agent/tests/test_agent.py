import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, AIMessageChunk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.agent import Agent
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
    """
    Pytest fixture som oppretter en Agent med mocket avhengigheter.

    Eksempel bruk:
    def test_something(mock_agent):
        # mock_agent er allerede konfigurert med mocks
        pass
    """
    with patch('agent.agent.ChromaVectorStore') as mock_chroma, \
         patch('agent.agent.BQVectorStore') as mock_bq, \
         patch('agent.agent.DocumentProcessor') as mock_doc_processor, \
         patch('agent.agent.Summarizer') as mock_summarizer, \
         patch('agent.agent.SupabaseStorageManager') as mock_storage, \
         patch('agent.agent.SupabaseManager') as mock_conversation_manager, \
         patch('agent.agent.ContextManager') as mock_context_manager, \
         patch('agent.agent.ToolManager') as mock_tool_manager:

        # Configure mock instances
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

        # Create agent with empty tools and basic prompt
        agent = Agent(
            tools=[],
            prompt="You are a helpful legal assistant."
        )

        # Replace instances with mocks for easier access
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
    """Consecutive HumanMessages (e.g. factsheet + user query) should be merged."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Factsheet context"),
        HumanMessage(content="User question"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 2  # System + merged Human
    assert isinstance(result[1], HumanMessage)
    assert "Factsheet context" in result[1].content
    assert "User question" in result[1].content


def test_sanitize_payload_merges_consecutive_ai_messages(mock_agent):
    """Consecutive AIMessages (e.g. summary + truncated AI) should be merged."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(content="Summary of conversation"),
        AIMessage(content="Actual response"),
    ]
    result = mock_agent._sanitize_payload(payload)
    assert len(result) == 3  # System + Human + merged AI
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
        HumanMessage(content="Q2"),  # No ToolMessage between AI and next Human
        AIMessage(content="A2"),
    ]
    result = mock_agent._sanitize_payload(payload)
    # The orphan AI with tool_calls should have tool_calls stripped
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
    assert result[2].tool_calls  # tool_calls preserved


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
    # Verify alternation: system, human, ai(tool), tool, ai, human, ai
    types = [type(m).__name__ for m in result]
    assert types == ["SystemMessage", "HumanMessage", "AIMessage", "ToolMessage", "AIMessage", "HumanMessage", "AIMessage"]


def test_sanitize_payload_ai_list_content_with_tool_calls(mock_agent):
    """AIMessage with list content AND tool_calls should normalize content and keep tool_calls."""
    payload = [
        SystemMessage(content="system"),
        HumanMessage(content="Q1"),
        AIMessage(
            content=[{"type": "text", "text": "Let me check"}],
            tool_calls=[{"name": "search", "args": {}, "id": "tc1"}]
        ),
        ToolMessage(content="result", tool_call_id="tc1", name="search"),
        AIMessage(content="Done"),
    ]
    result = mock_agent._sanitize_payload(payload)
    ai_with_tools = result[2]
    assert isinstance(ai_with_tools.content, str)
    assert ai_with_tools.content == "Let me check"
    assert ai_with_tools.tool_calls


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
    assert len(result) == 3  # System + merged Human + AI
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
    state = {"messages": [ai_msg]}

    result = mock_agent._should_continue(state)
    assert result is True


def test_should_continue_without_tool_calls(mock_agent):
    """Test _should_continue returns False when there are no tool calls."""
    ai_msg = get_mock_ai_message()
    state = {"messages": [ai_msg]}

    result = mock_agent._should_continue(state)
    assert result is False


def test_pick_llm_google(mock_agent):
    """Test _pick_llm with google provider."""
    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        mock_agent._pick_llm("google_gemini-2.5-flash")

        mock_init.assert_called_once_with("gemini-2.5-flash", model_provider="google_genai")


def test_pick_llm_openai(mock_agent):
    """Test _pick_llm with openai provider."""
    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        mock_agent._pick_llm("openai_gpt-4o")

        mock_init.assert_called_once_with("gpt-4o", model_provider="openai")


def test_pick_llm_unknown_provider(mock_agent):
    """Test _pick_llm with unknown provider defaults to google_genai."""
    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        mock_agent._pick_llm("unknown_some-model")

        mock_init.assert_called_once_with("some-model", model_provider="google_genai")


def test_load_msg_as_document(mock_agent):
    """Test _load_msg_as_document conversion."""
    msg = {
        "type": "human",
        "data": {
            "content": "Test message content",
            "id": "msg-001",
            "additional_kwargs": {"key": "value"}  # Should be filtered out (not simple type)
        }
    }

    doc = mock_agent._load_msg_as_document(msg)

    assert doc.page_content == "Test message content"
    assert doc.metadata["type"] == "human"
    assert doc.metadata["id"] == "msg-001"


def test_load_messages_as_document(mock_agent):
    """Test _load_messages_as_document batch conversion."""
    messages = [
        {"type": "human", "data": {"content": "Message 1", "id": "msg-001"}},
        {"type": "ai", "data": {"content": "Message 2", "id": "msg-002"}}
    ]

    docs = mock_agent._load_messages_as_document(messages)

    assert len(docs) == 2
    assert docs[0].page_content == "Message 1"
    assert docs[1].page_content == "Message 2"


# ============================================
#           CALL LLM TESTS
# ============================================

@pytest.mark.asyncio
async def test_call_llm_basic(mock_agent):
    """Test _call_llm basic invocation."""
    state = {
        "messages": [
            SystemMessage(content="System prompt"),
            HumanMessage(
                content="Test question",
                additional_kwargs={
                    "query_id": "query-001",
                    "session_id": "session-001",
                    "attachments": []
                }
            )
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = get_mock_ai_message()

    config = {"configurable": {"custom_project_id": None, "query_id": "query-001"}}
    mock_agent.conversation_manager.load_project.return_value = None

    result = await mock_agent._call_llm(state, mock_llm, config)

    mock_llm.ainvoke.assert_called_once()
    assert "messages" in result


@pytest.mark.asyncio
async def test_call_llm_with_project_data(mock_agent):
    """Test _call_llm includes factsheet when project data exists."""
    from tests.fixtures.context_manager_data import get_mock_factsheet,get_mock_attachments
    return_value = get_mock_factsheet()
    state = {
        "messages": [
            SystemMessage(content="System prompt"),
            HumanMessage(
                content="Test question",
                additional_kwargs={
                    "query_id": "query-001",
                    "session_id": "session-001",
                    "attachments": []
                }
            )
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = get_mock_ai_message()

    config = {"configurable": {"custom_project_id": "project-001", "query_id": "query-001"}}
    mock_agent.conversation_manager.load_factsheet.return_value = return_value

    result = await mock_agent._call_llm(state, mock_llm, config)

    mock_agent.conversation_manager.load_factsheet.assert_called_once_with(project_id="project-001", limited=False)
    assert "messages" in result


@pytest.mark.asyncio
async def test_call_llm_with_attachments(mock_agent):
    """Test _call_llm retrieves attachment content from vector store."""
    attachments = [{"file_id": "file-001", "filename": "test.pdf"}]
    state = {
        "messages": [
            SystemMessage(content="System prompt"),
            HumanMessage(
                content="Test question",
                additional_kwargs={
                    "query_id": "query-001",
                    "session_id": "session-001",
                    "attachments": attachments
                }
            )
        ]
    }

    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = get_mock_ai_message()

    config = {"configurable": {"custom_project_id": None, "query_id": "query-001"}}
    mock_agent.conversation_manager.load_project.return_value = None
    #mock_agent.in_memory_store.query.return_value = get_mock_vector_store_docs()

    result = await mock_agent._call_llm(state, mock_llm, config)

    #mock_agent.in_memory_store.query.assert_called_once()
    assert "messages" in result


# ============================================
#           CALL TOOL TESTS
# ============================================

@pytest.mark.asyncio
async def test_call_tool_no_tool_calls(mock_agent):
    """Test _call_tool with no tool calls returns empty messages."""
    ai_msg = get_mock_ai_message()  # No tool calls
    state = {"messages": [ai_msg]}

    result = await mock_agent._call_tool(state, query_id="query-001")

    assert result["messages"] == []


@pytest.mark.asyncio
async def test_call_tool_with_tool_calls(mock_agent):
    """Test _call_tool executes tool and returns result."""
    # Create a mock tool
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
    state = {"messages": [ai_msg]}

    result = await mock_agent._call_tool(state, query_id="query-001")

    mock_tool.ainvoke.assert_called_once()
    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)


@pytest.mark.asyncio
async def test_call_tool_invalid_tool_name(mock_agent):
    """Test _call_tool handles invalid tool name gracefully."""
    mock_agent.tools = []  # No tools available

    ai_msg = AIMessage(
        content="",
        id="ai-001",
        tool_calls=[{"name": "nonexistent_tool", "args": {}, "id": "tool-call-001"}]
    )
    state = {"messages": [ai_msg]}

    result = await mock_agent._call_tool(state, query_id="query-001")

    assert len(result["messages"]) == 1
    assert "Incorrect Tool Name" in result["messages"][0].content


# ============================================
#           INITIALIZE PROJECT TESTS
# ============================================

@pytest.mark.asyncio
async def test_initialize_project(mock_agent):
    """Test initialize_project creates factsheet from input and attachments."""
    query = get_mock_ask_agent_request_with_attachments()
    user_id = "user-001"

    # Setup mocks
    mock_agent.context_manager.analyze_init_input = AsyncMock(return_value=get_mock_initial_input())
    mock_agent.context_manager.analyze_docs = AsyncMock(return_value=get_mock_analyzed_doc())
    mock_agent.document_processor.process_attachment.return_value = get_mock_vector_store_docs()
    mock_agent.storage.save_raw_documents = AsyncMock()

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = None
        async for chunk in mock_agent.initialize_project(query, user_id):
            if chunk.get("type") == "result":
                result = chunk.get("data")

    assert result is not None
    assert "factsheet" in result
    assert "attachments" in result
    mock_agent.conversation_manager.save_project.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_project_no_attachments(mock_agent):
    """Test initialize_project with no attachments."""
    query = get_mock_ask_agent_request()  # No attachments
    user_id = "user-001"

    mock_agent.context_manager.analyze_init_input = AsyncMock(return_value=get_mock_initial_input())
    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = None
        async for chunk in mock_agent.initialize_project(query, user_id):
            if chunk.get("type") == "result":
                result = chunk.get("data")

    assert result is not None
    assert "factsheet" in result
    assert result["attachments"] == []


# ============================================
#           UPDATE PROJECT TESTS
# ============================================

@pytest.mark.asyncio
async def test_update_project(mock_agent):
    """Test update_project adds new attachments to existing project."""
    from tests.fixtures.context_manager_data import get_mock_factsheet,get_mock_attachments
    query = get_mock_ask_agent_request_with_attachments()
    user_id = "user-001"

    mock_agent.conversation_manager.load_factsheet.return_value = get_mock_factsheet()
    mock_agent.context_manager.analyze_docs = AsyncMock(return_value=get_mock_analyzed_doc())
    mock_agent.document_processor.parse.return_value = get_mock_vector_store_docs()
    mock_agent.document_processor.to_plain_text.return_value = "parsed plain text content"
    mock_agent.storage.save_raw_documents = AsyncMock()

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = None
        async for chunk in mock_agent.update_project(query, user_id):
            if chunk.get("type") == "result":
                result = chunk.get("data")

    assert result is not None
    assert "events" in result
    assert "attachments" in result
    #assert "emails" in result

@pytest.mark.asyncio
async def test_update_project_invalid_project_data(mock_agent):
    """Test update_project raises error with invalid project data."""
    query = get_mock_ask_agent_request()
    user_id = "user-001"

    # Return invalid data type
    mock_agent.conversation_manager.load_factsheet.return_value = "invalid_data"

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        with pytest.raises(TypeError):
            async for chunk in mock_agent.update_project(query, user_id):
                pass


# ============================================
#           CLEANUP ELEMENT TESTS
# ============================================

@pytest.mark.asyncio
async def test_cleanup_element_events(mock_agent):
    """Test cleanup_element cleans events."""
    query = get_mock_ask_agent_request()
    from tests.fixtures.context_manager_data import get_mock_factsheet

    mock_agent.conversation_manager.load_project.return_value = ProjectData(
        factsheet=get_mock_factsheet(),
        attachments=[],
        emails=[]
    )
    mock_agent.context_manager.clean_element = AsyncMock(return_value=[
        {"event_id": "cleaned-event-001", "event_date": "2023-08-15"}
    ])

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = None
        async for chunk in mock_agent.cleanup_element(query, element_type="events"):
            if chunk.get("type") == "result":
                result = chunk.get("data")

    assert result is not None
    assert result["success"] is True
    mock_agent.conversation_manager.replace_project_element.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_element_invalid_type(mock_agent):
    """Test cleanup_element raises error for invalid element type."""
    query = get_mock_ask_agent_request()

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        with pytest.raises(ValueError):
            async for chunk in mock_agent.cleanup_element(query, element_type="invalid_type"):
                pass


# ============================================
#           STREAM EVENT HANDLERS
# ============================================

def test_on_chat_model_stream(mock_agent):
    """Test on_chat_model_stream extracts token from chunk."""
    chunk = AIMessageChunk(content="Hello")
    data = {"chunk": chunk}

    result = mock_agent.on_chat_model_stream(data, query_id="query-001", token_stream="")

    assert result["type"] == "token"
    assert result["data"] == "Hello"
    assert result["query_id"] == "query-001"


def test_on_chat_model_stream_no_chunk(mock_agent):
    """Test on_chat_model_stream returns None when no chunk."""
    data = {"chunk": None}

    result = mock_agent.on_chat_model_stream(data, query_id="query-001", token_stream="")

    assert result is None


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
#           COMPILE AGENT TESTS
# ============================================

def test_compile_agent(mock_agent):
    """Test _compile_agent creates a runnable graph."""
    with patch('agent.agent.init_chat_model') as mock_init:
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_init.return_value = mock_llm

        agent_instance = mock_agent._compile_agent(
            llm_model="google_gemini-2.5-flash",
            query_id="query-001"
        )

        # The compiled agent should have astream_events method
        assert hasattr(agent_instance, 'astream_events')
        mock_llm.bind_tools.assert_called_once()


# ============================================
#           LOAD OR CREATE CONVERSATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_load_or_create_conversation_new(mock_agent):
    """Test load_or_create_conversation creates new conversation."""
    mock_agent_instance = AsyncMock()
    mock_agent_instance.aget_state.return_value = MagicMock(values={"messages": []})

    thread = {"configurable": {"thread_id": "session-001"}}

    await mock_agent.load_or_create_conversation(mock_agent_instance, thread, "session-001")

    mock_agent_instance.aupdate_state.assert_called_once()


@pytest.mark.asyncio
async def test_load_or_create_conversation_existing(mock_agent):
    """Test load_or_create_conversation continues existing conversation."""
    mock_agent_instance = AsyncMock()
    mock_agent_instance.aget_state.return_value = MagicMock(
        values={"messages": [HumanMessage(content="Previous message")]}
    )

    thread = {"configurable": {"thread_id": "session-001"}}

    await mock_agent.load_or_create_conversation(mock_agent_instance, thread, "session-001")

    # Should not update state for existing conversation
    mock_agent_instance.aupdate_state.assert_not_called()


# ============================================
#      INITIALIZE PROJECT INTEGRATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_initialize_project_with_mocks(mock_agent):
    """Integration test: initialize_project with mocked LLM (fast, for CI/CD)"""
    # Setup mock responses for the entire flow
    mock_initial_input = InitialInput(
        title="Test Eiendomssak",
        background="Test case about property dispute",
        parties=[
            Party(
                party_id="party-001",
                legal_name="Test Plaintiff",
                role="plaintiff",
                entity_type="individual"
            )
        ]
    )
    
    mock_analyzed_doc_result = {
        "attachments": [Attachment(
            file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3",
            filename="test.pdf",
            path="user/session/test.pdf",
            file_type="application/pdf",
            size=1000,
            description="Test document",
            significance="high",
            category="agreement"
        )],
        "events": [
            Event(
                event_id="event-001",
                event_name="Contract Signed",
                event_start_date=datetime(2023, 8, 25),
                description="Purchase contract signed",
                category="contract_signing",
                parties=["plaintiff", "defendant"],
                significance="high",
                disputed=False,
                file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3"
            )
        ],
        "damages": [],
        "claims": [],
        "deadlines": []
    }
    
    # Configure context_manager mocks
    mock_agent.context_manager.analyze_init_input = AsyncMock(return_value=mock_initial_input)
    mock_agent.context_manager.analyze_docs = AsyncMock(return_value=mock_analyzed_doc_result)
    mock_agent.context_manager.analyze_emails = AsyncMock(return_value=mock_analyzed_doc_result)
    mock_agent.context_manager.analyze_doc = AsyncMock(return_value=mock_analyzed_doc_result)
    
    # Configure storage mocks
    mock_agent.storage.save_raw_documents = AsyncMock(return_value={"status": "success"})
    mock_agent.vs.add_documents = MagicMock(return_value=None)
    mock_agent.conversation_manager.save_project = MagicMock(return_value=None)
    
    # Create request
    request = get_mock_ask_agent_request_with_attachments()
    
    # Run initialize_project
    results = []
    async for chunk in mock_agent.initialize_project(
        query=request,
        user_id="test-user-001"
    ):
        results.append(chunk)
    
    # Verify we got status updates and final result
    assert len(results) > 0
    
    # Check for status updates in correct phases
    status_types = [r.get("type") for r in results]
    assert "status" in status_types
    assert "result" in status_types
    
    # Get final result
    final_result = next((r for r in results if r.get("type") == "result"), None)
    assert final_result is not None
    assert "factsheet" in final_result["data"]
    assert "attachments" in final_result["data"]
    
    # Verify factsheet structure
    print(f'=======FINAL RESULT====\n{final_result}\n\n')
    factsheet = final_result["data"]["factsheet"]
    assert factsheet["title"] == "Test Eiendomssak"
    assert len(factsheet["events"]) >= 1, "Should have at least one event from documents"
    assert len(factsheet["parties"]) >= 1, "Should have at least one party"
    
    # Verify context_manager calls
    mock_agent.context_manager.analyze_init_input.assert_called_once()
    assert mock_agent.context_manager.analyze_docs.call_count >= 1
    
    # Verify storage calls
    mock_agent.storage.save_raw_documents.assert_called_once()
    mock_agent.conversation_manager.save_project.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_initialize_project_real_llm_small_input():
    """Integration test: initialize_project with real LLM and minimal data
    
    This test uses REAL API calls to verify the entire initialize_project flow.
    Requires: GOOGLE_API_KEY or GEMINI_API_KEY
    """
    from base64 import b64encode
    # Mock saving and BigQuery
    with patch('agent.agent.SupabaseManager.save_project') as mock_save_project, \
         patch('agent.agent.BQVectorStore') as mock_bq:
        
        mock_save_project.return_value = None
        
        # Mock BQ vector store instance
        mock_bq_instance = MagicMock()
        mock_bq_instance.add_documents = MagicMock(return_value=None)
        mock_bq.return_value = mock_bq_instance
        mock_bq_instance.embedding_model = "mock_embedding_model"
        
        agent = Agent(
            tools=[],
            prompt="You are a helpful legal assistant analyzing case documents."
        )
        content_txt = """SAKSAMMENDRAG

Kjøper: Andreas Nilsen og Berit Johansen
Selger: Daniel Hansen og Camilla Hansen
Eiendom: Granveien 15B, Oslo
Kjøpesum: NOK 15 500 000
Kontraktsdato: 25. august 2023
Overtakelse: 11. november 2023

Mangler oppdaget:
- Elektriske feil (flere stikkontakter fungerer ikke)
- Problemer med pipa/skorstein

Reklamasjon sendt til selger: 15. desember 2023
"""
        # Create minimal request with simple text attachment
        request = AskAgentRequest(
            question="""Vi har en tvist om eiendomskjøp. 
        Meg (Andreas Nilsen) og min kone Berit kjøpte hus fra Daniel og Camilla Hansen.
        Kontrakten ble signert 25. august 2023 for 15.5 millioner kroner.
        Vi overtok boligen 11. november 2023.
        Etter overtakelsen oppdaget vi elektriske feil og problemer med pipa.""",

        
            session_id="integration-test-session-001",
            query_id="integration-test-query-001",
            project_id="integration-test-project-001",
            llm_model="google_gemini-2.5-pro",
            attachments=[
                AttachmentModel(
                    file_id="integration-test-file-001",
                    filename="simple_case_summary.txt",
                    file_type="text/plain",
                    content=b64encode(content_txt.encode("utf-8")), 
                    size=350,
                    path="integration-test/integration-test-session-001/integration-test-file-001.txt",
                    query_id="integration-test-query-001"
                )
            ]
        )
        
        # Run initialize_project with real LLM
        results = []
        async for chunk in agent.initialize_project(
            query=request,
            user_id="integration-test-user-001"
        ):
            results.append(chunk)
        
        # Verify we got results
        assert len(results) > 0, "Should receive status updates and final result"
        
        # Check for required phases
        phases_seen = set()
        for result in results:
            if result.get("type") == "status":
                phase = result.get("phase", [])
                if isinstance(phase, list):
                    phases_seen.update(phase)
                else:
                    phases_seen.add(phase)
        
        # Should see key phases
        assert "initialization" in phases_seen or "init_input" in phases_seen
        assert "analyze_docs" in phases_seen or "analyze_doc" in phases_seen
        assert "final_analysis" in phases_seen or "analyze_docs" in phases_seen
        
        # Get final result
        final_result = next((r for r in results if r.get("type") == "result"), None)
        assert final_result is not None, "Should have final result chunk"
        assert "data" in final_result
        assert "factsheet" in final_result["data"]

        print(f'\n\n FINAL RESULT \n\n {final_result["data"].get("factsheet")}\n\n {final_result["data"].get("attachments")}\n\n {final_result["data"].get("emails")}\n\n')
        
        # Verify factsheet has expected structure
        factsheet = final_result["data"]["factsheet"]
        
        # Should have analyzed parties (Andreas, Berit, Daniel, Camilla)
        assert "parties" in factsheet
        assert len(factsheet["parties"]) >= 2, "Should identify at least buyers and sellers"
        
        # Should have events (contract signing, takeover, etc)
        assert "events" in factsheet
        assert len(factsheet["events"]) >= 1, "Should identify key events like contract signing"
        
        # Attachments should be processed
        assert "attachments" in final_result["data"]
        assert len(final_result["data"]["attachments"]) == 1


@pytest.mark.asyncio
@pytest.mark.integration  
async def test_initialize_project_with_email_without_saving():
    """Integration test: initialize_project with email attachment and real LLM
    
    Tests email parsing and analysis flow end-to-end.
    Requires: GOOGLE_API_KEY or GEMINI_API_KEY
    """
    from tests.fixtures.email_data import get_mock_eml_plain_text_b64
    from dotenv import load_dotenv
    load_dotenv()
    
    # Set absolute path to gcloud credentials if using relative path
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "gcloud-keys.json")
    if not os.path.isabs(creds_path):
        # Convert to absolute path relative to agent directory
        agent_dir = os.path.join(os.path.dirname(__file__), '..')
        creds_path = os.path.join(agent_dir, creds_path)
    
    if not os.path.exists(creds_path):
        pytest.skip(f"Google Cloud credentials not found at {creds_path}. Skipping integration test.")
    
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

    # Mock saving and BigQuery to avoid needing actual BQ setup
    with patch('agent.agent.SupabaseManager.save_project') as mock_save_project, \
         patch('agent.agent.BQVectorStore') as mock_bq:
        
        mock_save_project.return_value = None
        
        # Mock BQ vector store instance
        mock_bq_instance = MagicMock()
        mock_bq_instance.add_documents = MagicMock(return_value=None)
        mock_bq_instance.embedding_model = "mock_embedding_model"
        mock_bq.return_value = mock_bq_instance
        
        # Create real agent (with mocked BQ)
        agent = Agent(
            tools=[],
            prompt="You are a helpful legal assistant."
        )
        
        # Create request with email attachment
        request = AskAgentRequest(
            question="Analyser denne emailen i forbindelse med eiendomssaken.",
            session_id="integration-email-session-001",
            query_id="integration-email-query-001", 
            project_id="integration-email-project-001",
            llm_model="google_gemini-2.5-flash",
            attachments=[
                AttachmentModel(
                    file_id="integration-email-file-001",
                    filename="test-email.eml",
                    file_type="message/rfc822",
                    content=get_mock_eml_plain_text_b64(),
                    size=1500,
                    path="integration-test/integration-email-session-001/integration-email-file-001.eml",
                    query_id="integration-email-query-001"
                )
            ]
        )
        
        # Run initialize_project
        results = []
        async for chunk in agent.initialize_project(
            query=request,
            user_id="integration-test-user-001"
        ):
            results.append(chunk)
        
        # Verify results
        assert len(results) > 0
        
        # Should have email analysis phase
        phases = [r.get("phase", []) for r in results if r.get("type") == "status"]
        all_phases = []
        for phase in phases:
            if isinstance(phase, list):
                all_phases.extend(phase)
            else:
                all_phases.append(phase)
        
        # Either analyze_email or analyze_doc should be present
        assert any("email" in str(p).lower() or "doc" in str(p).lower() for p in all_phases)
        
        # Get final result
        final_result = next((r for r in results if r.get("type") == "result"), None)
        assert final_result is not None
        
        # Should have processed the email
        factsheet = final_result["data"]["factsheet"]
        assert factsheet is not None


@pytest.mark.asyncio
async def test_initialize_project_empty_attachments(mock_agent):
    """Integration test: initialize_project with no attachments"""
    # Setup minimal mocks
    mock_initial_input = InitialInput(
        title="Minimal Test Case",
        background="Just a question without documents",
        parties=[]
    )
    
    mock_agent.context_manager.analyze_init_input = AsyncMock(return_value=mock_initial_input)
    mock_agent.conversation_manager.save_project = MagicMock(return_value=None)
    
    # Request without attachments
    request = get_mock_ask_agent_request()
    
    # Run initialize_project
    results = []
    async for chunk in mock_agent.initialize_project(
        query=request,
        user_id="test-user-001"
    ):
        results.append(chunk)
    
    # Should still get results
    assert len(results) > 0
    
    # Should have final result
    final_result = next((r for r in results if r.get("type") == "result"), None)
    assert final_result is not None
    
    # Factsheet should exist but with empty events/files
    factsheet = final_result["data"]["factsheet"]
    assert factsheet["events"] == []
    assert len(final_result["data"]["attachments"]) == 0
