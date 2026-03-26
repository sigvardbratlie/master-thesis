import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.pipelines import ProjectPipeline
from models import PipelineState, AskAgentRequest, InitialInput, ProjectData, FactSheet, Party, Attachment, Event
from tests.fixtures.agent_data import (
    get_mock_ask_agent_request,
    get_mock_ask_agent_request_with_attachments,
    get_mock_initial_input,
    get_mock_analyzed_doc,
    get_mock_vector_store_docs,
)
from tests.fixtures.context_manager_data import get_mock_factsheet, get_mock_attachments


MOCK_THREAD_CONFIG = {
    "configurable": {
        "user_id": "user-001",
        "llm_model": "google_gemini-2.5-flash",
        "thread_id": "session-001",
        "custom_project_id": "project-001",
    },
    "metadata": {"query_id": "query-001"},
}


@pytest.fixture
def mock_pipeline():
    """Creates a ProjectPipeline with mocked dependencies."""
    with patch('agent.pipelines.ContextManager') as mock_cm, \
         patch('agent.pipelines.DocumentProcessor') as mock_dp, \
         patch('agent.pipelines.SupabaseStorageManager') as mock_storage, \
         patch('agent.pipelines.BQVectorStore') as mock_bq, \
         patch('agent.pipelines.SupabaseManager') as mock_db:

        mock_cm_instance = MagicMock()
        mock_cm.return_value = mock_cm_instance

        mock_dp_instance = MagicMock()
        mock_dp.return_value = mock_dp_instance

        mock_storage_instance = MagicMock()
        mock_storage.return_value = mock_storage_instance

        mock_bq_instance = MagicMock()
        mock_bq.return_value = mock_bq_instance
        mock_bq_instance.embedding_model = "mock-embedding-model"

        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        mock_config = MagicMock()
        mock_config.async_tasks.max_concurrent_requests = 3
        mock_config.async_tasks.throttle_value = 0
        mock_config.project.embed_to_vectorstore = True
        mock_config.project.save_to_storage = True
        mock_config.project.threshold = 5120000
        mock_config.project.max_attachments = 10
        mock_config.project.max_emails = 15

        pipeline = ProjectPipeline(name="test-pipeline", config=mock_config)
        pipeline.context_manager = mock_cm_instance
        pipeline.document_processor = mock_dp_instance
        pipeline.storage = mock_storage_instance
        pipeline.vs = mock_bq_instance
        pipeline.conversation_manager = mock_db_instance

        yield pipeline


# ============================================
#           INIT AND COMPILE TESTS
# ============================================

def test_pipeline_init(mock_pipeline):
    """ProjectPipeline should initialize with expected attributes."""
    assert mock_pipeline.name == "test-pipeline"
    assert mock_pipeline.context_manager is not None
    assert mock_pipeline.document_processor is not None
    assert mock_pipeline.storage is not None
    assert mock_pipeline.vs is not None
    assert mock_pipeline.conversation_manager is not None


def test_compile_init_pipeline(mock_pipeline):
    """compile_init_pipeline should produce a runnable LangGraph graph."""
    graph = mock_pipeline.compile_init_pipeline()
    assert hasattr(graph, 'astream_events')


def test_compile_update_pipeline(mock_pipeline):
    """compile_update_pipeline should produce a runnable LangGraph graph."""
    graph = mock_pipeline.compile_update_pipeline()
    assert hasattr(graph, 'astream_events')


# ============================================
#           COLLAPSE EMAILS NODE
# ============================================

def test_collapse_emails_node_no_emails(mock_pipeline):
    """Returns empty collapsed_emails when no email attachments."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query)

    mock_writer = MagicMock()
    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        result = mock_pipeline._collapse_emails_node(state)

    assert result["collapsed_emails"] == {}
    mock_writer.assert_called()


def test_collapse_emails_node_no_attachments_at_all(mock_pipeline):
    """Returns empty collapsed_emails when query has no attachments."""
    query = AskAgentRequest(
        question="Test",
        session_id="session-001",
        query_id="query-001",
        project_id="project-001",
        llm_model="google_gemini-2.5-flash",
        attachments=None
    )
    state = PipelineState(query=query)

    mock_writer = MagicMock()
    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        result = mock_pipeline._collapse_emails_node(state)

    assert result["collapsed_emails"] == {}


# ============================================
#           STORAGE NODE
# ============================================

@pytest.mark.asyncio
async def test_storage_node(mock_pipeline):
    """Storage node calls save_raw_documents."""
    query = get_mock_ask_agent_request_with_attachments()
    state = PipelineState(query=query)

    mock_pipeline.storage.save_raw_documents = AsyncMock(return_value=True)
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        await mock_pipeline._storage_node(state)

    mock_pipeline.storage.save_raw_documents.assert_called_once()


@pytest.mark.asyncio
async def test_storage_node_no_attachments(mock_pipeline):
    """Storage node still runs with empty attachments."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query)

    mock_pipeline.storage.save_raw_documents = AsyncMock(return_value=True)
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        await mock_pipeline._storage_node(state)

    mock_pipeline.storage.save_raw_documents.assert_called_once()


# ============================================
#           INITIALIZE INPUT NODE
# ============================================

@pytest.mark.asyncio
async def test_initialize_input_node(mock_pipeline):
    """_initialize_input_node calls analyze_init_input and returns InitialInput."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query)

    mock_initial_input = get_mock_initial_input()
    mock_pipeline.context_manager.analyze_init_input = AsyncMock(return_value=mock_initial_input)

    mock_writer = MagicMock()
    mock_llm = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.pipelines.pick_llm', return_value=mock_llm):
        result = await mock_pipeline._initialize_input_node(state)

    assert "input_" in result
    assert isinstance(result["input_"], InitialInput)
    mock_pipeline.context_manager.analyze_init_input.assert_called_once()


# ============================================
#           PARSING NODE
# ============================================

@pytest.mark.asyncio
async def test_parsing_node_no_attachments(mock_pipeline):
    """_parsing_node returns empty docs_by_file when no attachments."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query)

    mock_writer = MagicMock()
    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG):
        result = await mock_pipeline._parsing_node(state)

    assert result["docs_by_file"] == {}


@pytest.mark.asyncio
async def test_parsing_node_with_attachments(mock_pipeline):
    """_parsing_node parses attachments and builds docs_by_file."""
    query = get_mock_ask_agent_request_with_attachments()
    state = PipelineState(query=query)

    mock_docs = get_mock_vector_store_docs()
    mock_pipeline.document_processor.parse_to_docs.return_value = mock_docs
    mock_pipeline.document_processor.to_plain_text.return_value = "plain text content"

    mock_writer = MagicMock()
    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG):
        result = await mock_pipeline._parsing_node(state)

    assert "docs_by_file" in result
    assert len(result["docs_by_file"]) > 0


# ============================================
#           EMBEDDING NODE
# ============================================

@pytest.mark.asyncio
async def test_embedding_node_no_docs(mock_pipeline):
    """_embedding_node skips vectorstore when no docs."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query, docs_by_file={})

    mock_pipeline.embed_to_vectorstore = True
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        await mock_pipeline._embedding_node(state)

    mock_pipeline.vs.add_documents.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_node_disabled(mock_pipeline):
    """_embedding_node skips vectorstore when embed_to_vectorstore is False."""
    query = get_mock_ask_agent_request_with_attachments()
    mock_docs = get_mock_vector_store_docs()
    state = PipelineState(query=query, docs_by_file={"file-001": mock_docs})

    mock_pipeline.config.project.embed_to_vectorstore = False
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        await mock_pipeline._embedding_node(state)

    mock_pipeline.vs.add_documents.assert_not_called()


@pytest.mark.asyncio
async def test_embedding_node_with_docs(mock_pipeline):
    """_embedding_node calls vs.add_documents when embed_to_vectorstore is enabled."""
    query = get_mock_ask_agent_request_with_attachments()
    mock_docs = get_mock_vector_store_docs()
    state = PipelineState(query=query, docs_by_file={"file-001": mock_docs})

    mock_pipeline.embed_to_vectorstore = True
    mock_pipeline.vs.add_documents = MagicMock()
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer):
        await mock_pipeline._embedding_node(state)

    mock_pipeline.vs.add_documents.assert_called_once()


# ============================================
#           SAVE INIT NODE
# ============================================

@pytest.mark.asyncio
async def test_save_init_node(mock_pipeline):
    """_save_init_node saves project and writes final result via stream."""
    query = get_mock_ask_agent_request()
    initial_input = get_mock_initial_input()
    analyzed = get_mock_analyzed_doc()

    state = PipelineState(
        query=query,
        input_=initial_input,
        attachments=[analyzed["file"]],
        events=analyzed["events"],
        damages=[],
        claims=[],
        deadlines=[],
        emails=[],
    )

    mock_pipeline.conversation_manager.save_project = MagicMock()
    writer_calls = []
    mock_writer = MagicMock(side_effect=lambda x: writer_calls.append(x))

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG):
        await mock_pipeline._save_init_node(state)

    mock_pipeline.conversation_manager.save_project.assert_called_once()
    result_calls = [c for c in writer_calls if isinstance(c, dict) and c.get("type") == "result"]
    assert len(result_calls) == 1
    assert "factsheet" in result_calls[0]["data"]
    assert "attachments" in result_calls[0]["data"]
    assert "emails" in result_calls[0]["data"]


# ============================================
#           LOAD PROJECT DATA NODE
# ============================================

@pytest.mark.asyncio
async def test_load_project_data_returns_project(mock_pipeline):
    """_load_project_data returns ProjectData when project exists."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query)

    mock_project = ProjectData(
        factsheet=get_mock_factsheet(),
        attachments=[],
        emails=[]
    )
    mock_pipeline.conversation_manager.load_project.return_value = mock_project
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG):
        result = await mock_pipeline._load_project_data(state)

    assert "input_" in result
    assert isinstance(result["input_"], ProjectData)


@pytest.mark.asyncio
async def test_load_project_data_invalid_type_raises(mock_pipeline):
    """_load_project_data raises TypeError when load_project returns wrong type."""
    query = get_mock_ask_agent_request()
    state = PipelineState(query=query)

    mock_pipeline.conversation_manager.load_project.return_value = "invalid_data"
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG), \
         pytest.raises(TypeError):
        await mock_pipeline._load_project_data(state)


# ============================================
#           UPDATE METADATA NODE
# ============================================

@pytest.mark.asyncio
async def test_update_metadata_node_with_initial_input(mock_pipeline):
    """_update_metadata_node calls update_initial_input and returns updated InitialInput."""
    query = get_mock_ask_agent_request()
    initial_input = get_mock_initial_input()
    state = PipelineState(query=query, input_=initial_input)

    updated_input = InitialInput(title="Updated Title", background="Updated background", parties=[])
    mock_pipeline.context_manager.update_initial_input = AsyncMock(return_value=updated_input)
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.pipelines.pick_llm', return_value=MagicMock()):
        result = await mock_pipeline._update_metadata_node(state)

    assert "input_" in result
    mock_pipeline.context_manager.update_initial_input.assert_called_once()


@pytest.mark.asyncio
async def test_update_metadata_node_with_project_data(mock_pipeline):
    """_update_metadata_node handles ProjectData as input_ (update flow)."""
    query = get_mock_ask_agent_request()
    project_data = ProjectData(factsheet=get_mock_factsheet(), attachments=[], emails=[])
    state = PipelineState(query=query, input_=project_data)

    updated_input = get_mock_initial_input()
    mock_pipeline.context_manager.update_initial_input = AsyncMock(return_value=updated_input)
    mock_writer = MagicMock()

    with patch('agent.pipelines.get_stream_writer', return_value=mock_writer), \
         patch('agent.pipelines.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.pipelines.pick_llm', return_value=MagicMock()):
        result = await mock_pipeline._update_metadata_node(state)

    assert "input_" in result


# ============================================
#           MK UPDATE QUERY FROM SESSION
# ============================================

def test_mk_update_query_from_session_builds_query(mock_pipeline):
    """mk_update_query_from_session returns an AskAgentRequest with session context."""
    query = get_mock_ask_agent_request()

    mock_session = MagicMock()
    mock_session.attachments = []
    mock_session.events = [
        MagicMock(type="human", content="I need help with this case")
    ]
    mock_pipeline.conversation_manager.load_session_history.return_value = mock_session

    result = mock_pipeline.mk_update_query_from_session(query)

    assert isinstance(result, AskAgentRequest)
    assert result.project_id == query.project_id
    assert result.session_id == query.session_id


# ============================================
#           INTEGRATION TEST (mocked LLM)
# ============================================

@pytest.mark.asyncio
async def test_initialize_project_saves_project(mock_pipeline):
    """Integration: full pipeline run calls save_project and produces a FactSheet."""
    query = get_mock_ask_agent_request_with_attachments()
    initial_input = get_mock_initial_input()
    analyzed = get_mock_analyzed_doc()

    mock_pipeline.context_manager.analyze_init_input = AsyncMock(return_value=initial_input)
    mock_pipeline.context_manager.analyze_docs = AsyncMock(return_value={
        "attachments": [analyzed["file"]],
        "events": analyzed["events"],
        "damages": [],
        "claims": [],
        "deadlines": [],
        "_source_filenames": ["test.pdf"],
    })
    mock_pipeline.context_manager.update_initial_input = AsyncMock(return_value=initial_input)
    mock_pipeline.document_processor.parse_to_docs.return_value = get_mock_vector_store_docs()
    mock_pipeline.document_processor.to_plain_text.return_value = "plain text"
    mock_pipeline.storage.save_raw_documents = AsyncMock(return_value=True)
    mock_pipeline.vs.add_documents = MagicMock()
    mock_pipeline.conversation_manager.save_project = MagicMock()

    graph = mock_pipeline.compile_init_pipeline()

    thread = {
        "configurable": {
            "thread_id": query.session_id,
            "user_id": "test-user-001",
            "custom_project_id": query.project_id,
            "llm_model": query.llm_model,
        },
        "metadata": {"query_id": query.query_id},
    }

    with patch('agent.pipelines.pick_llm', return_value=MagicMock()):
        final_state = await graph.ainvoke({"query": query}, config=thread)

    mock_pipeline.conversation_manager.save_project.assert_called_once()
    mock_pipeline.storage.save_raw_documents.assert_called_once()

    # Pipeline should have collected attachments and events
    assert len(final_state["attachments"]) >= 1
    assert len(final_state["events"]) >= 1
