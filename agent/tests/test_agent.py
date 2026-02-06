import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage, AIMessageChunk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.agent import Agent
from agent.basemodels import *
from tests.fixtures.agent_data import (
    get_mock_ask_agent_request,
    get_mock_ask_agent_request_with_attachments,
    get_mock_project_data,
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

    assert "Retrieved context from user's documents" in result
    assert "Content of file 001" in result
    assert "Content of file 002" in result
    assert "test.pdf" in result


def test_build_attachment_context_without_user_input(mock_agent):
    """Test _build_attachment_context without user input triggers summarization."""
    attachments = [{"file_id": "file-001", "filename": "test.pdf", "path": "path/to/test.pdf"}]
    attachment_contents = {"file-001": "Content of file 001"}

    mock_agent.summarizer.summarize.return_value = "Summarized content"

    result = mock_agent._build_attachment_context(
        attachments=attachments,
        attachment_contents=attachment_contents,
        user_input=""  # Empty user input
    )

    mock_agent.summarizer.summarize.assert_called_once()
    assert "Summary of attachment contents" in result


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


def test_is_valid_uuid(mock_agent):
    """Test _is_valid_uuid validation."""
    valid_uuid = "123e4567-e89b-12d3-a456-426614174000"
    invalid_uuid = "not-a-uuid"

    assert mock_agent._is_valid_uuid(valid_uuid) is True
    assert mock_agent._is_valid_uuid(invalid_uuid) is False


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
    mock_agent.conversation_manager.load_project.return_value = get_mock_project_data()

    result = await mock_agent._call_llm(state, mock_llm, config)

    mock_agent.conversation_manager.load_project.assert_called_once_with(project_id="project-001")
    assert result["factsheet"] is not None


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
    mock_agent.in_memory_store.query.return_value = get_mock_vector_store_docs()

    result = await mock_agent._call_llm(state, mock_llm, config)

    mock_agent.in_memory_store.query.assert_called_once()
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
    mock_agent.context_manager.analyze_doc = AsyncMock(return_value=get_mock_analyzed_doc())
    mock_agent.context_manager.analyze_factual_facts = AsyncMock(return_value=FactualFacts(
        disputed_facts=["Fact 1"],
        undisputed_facts=["Fact 2"]
    ))
    mock_agent.context_manager.analyze_governing_law = AsyncMock(return_value=GoverningLaw(
        primary_jurisdiction="Norwegian law",
        key_areas=["Contract Law"],
        procedural_law="tvisteloven"
    ))
    mock_agent.document_processor.process_attachment.return_value = get_mock_vector_store_docs()
    mock_agent.storage.save_raw_documents = AsyncMock()

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = await mock_agent.initialize_project(query, user_id)

    assert "factsheet" in result
    assert "attachments" in result
    mock_agent.conversation_manager.save_project.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_project_no_attachments(mock_agent):
    """Test initialize_project with no attachments."""
    query = get_mock_ask_agent_request()  # No attachments
    user_id = "user-001"

    mock_agent.context_manager.analyze_init_input = AsyncMock(return_value=get_mock_initial_input())
    mock_agent.context_manager.analyze_factual_facts = AsyncMock(return_value=FactualFacts(
        disputed_facts=[],
        undisputed_facts=[]
    ))
    mock_agent.context_manager.analyze_governing_law = AsyncMock(return_value=GoverningLaw(
        primary_jurisdiction="Norwegian law",
        key_areas=[],
        procedural_law="tvisteloven"
    ))

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = await mock_agent.initialize_project(query, user_id)

    assert "factsheet" in result
    assert result["attachments"] == []


# ============================================
#           UPDATE PROJECT TESTS
# ============================================

@pytest.mark.asyncio
async def test_update_project(mock_agent):
    """Test update_project adds new attachments to existing project."""
    query = get_mock_ask_agent_request_with_attachments()
    user_id = "user-001"

    mock_agent.conversation_manager.load_project.return_value = get_mock_project_data()
    mock_agent.context_manager.consider_new_doc = AsyncMock(return_value=get_mock_analyzed_doc())
    mock_agent.document_processor.process_attachment.return_value = get_mock_vector_store_docs()
    mock_agent.storage.save_raw_documents = AsyncMock()

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = await mock_agent.update_project(query, user_id)

    assert "events" in result
    assert "attachments" in result


@pytest.mark.asyncio
async def test_update_project_invalid_project_data(mock_agent):
    """Test update_project raises error with invalid project data."""
    query = get_mock_ask_agent_request()
    user_id = "user-001"

    # Return invalid data type
    mock_agent.conversation_manager.load_project.return_value = "invalid_data"

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        with pytest.raises(TypeError):
            await mock_agent.update_project(query, user_id)


# ============================================
#           CLEANUP ELEMENT TESTS
# ============================================

@pytest.mark.asyncio
async def test_cleanup_element_events(mock_agent):
    """Test cleanup_element cleans events."""
    query = get_mock_ask_agent_request()

    mock_agent.conversation_manager.load_project.return_value = get_mock_project_data()
    mock_agent.context_manager.clean_element = AsyncMock(return_value=[
        {"event_id": "cleaned-event-001", "event_date": "2023-08-15"}
    ])

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        result = await mock_agent.cleanup_element(query, element_type="events")

    assert result["success"] is True
    mock_agent.conversation_manager.replace_project_element.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_element_invalid_type(mock_agent):
    """Test cleanup_element raises error for invalid element type."""
    query = get_mock_ask_agent_request()

    with patch('agent.agent.init_chat_model') as mock_init:
        mock_init.return_value = MagicMock()

        with pytest.raises(ValueError):
            await mock_agent.cleanup_element(query, element_type="invalid_type")


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
