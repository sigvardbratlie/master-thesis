import pytest
import sys
import os
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.clean import ProjectClean
from models import PipelineState, ProjectData, FactSheet, Party, Event
from models import CleanupElementsRequest
from tests.fixtures.agent_data import get_mock_ask_agent_request
from tests.fixtures.context_manager_data import get_mock_factsheet


MOCK_THREAD_CONFIG = {
    "configurable": {
        "user_id": "user-001",
        "llm_model": "google_gemini-2.5-flash",
        "thread_id": "session-001",
        "custom_project_id": "project-001",
    },
    "metadata": {"query_id": "query-001"},
}


def get_mock_cleanup_request(element_types: list[str] = None) -> CleanupElementsRequest:
    return CleanupElementsRequest(
        question="Cleanup",
        session_id="8fbac4e4-c2ff-4f58-95ba-7836f207a89d",
        query_id="0c22552d-8bee-4c24-a099-335c80db5573",
        project_id="ce119cd7-2c72-4400-8133-a08888b747ff",
        llm_model="google_gemini-2.5-flash",
        element_types=element_types or ["events"],
    )


@pytest.fixture
def mock_clean():
    """Creates a ProjectClean with mocked dependencies."""
    with patch('agent.clean.ContextManager') as mock_cm, \
         patch('agent.clean.DocumentProcessor') as mock_dp, \
         patch('agent.clean.SupabaseStorageManager') as mock_storage, \
         patch('agent.clean.BQVectorStore') as mock_bq, \
         patch('agent.clean.SupabaseManager') as mock_db:

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

        clean = ProjectClean(name="test-cleaner", config=mock_config)
        clean.context_manager = mock_cm_instance
        clean.document_processor = mock_dp_instance
        clean.storage = mock_storage_instance
        clean.vs = mock_bq_instance
        clean.conversation_manager = mock_db_instance

        yield clean


# ============================================
#           INIT AND COMPILE TESTS
# ============================================

def test_clean_init(mock_clean):
    """ProjectClean should initialize with expected attributes."""
    assert mock_clean.name == "test-cleaner"
    assert mock_clean.context_manager is not None
    assert mock_clean.conversation_manager is not None


def test_compile_clean_elements(mock_clean):
    """compile_clean_elements should produce a runnable LangGraph graph."""
    graph = mock_clean.compile_clean_elements()
    assert hasattr(graph, 'astream_events')


def test_compile_clean_metadata(mock_clean):
    """compile_clean_metadata should produce a runnable LangGraph graph."""
    graph = mock_clean.compile_clean_metadata()
    assert hasattr(graph, 'astream_events')


# ============================================
#           LOAD PROJECT NODE
# ============================================

@pytest.mark.asyncio
async def test_load_project_node_returns_project(mock_clean):
    """_load_project_node loads and returns ProjectData in state."""
    query = get_mock_cleanup_request(["events"])
    state = PipelineState(query=query)

    mock_clean.conversation_manager.load_factsheet.return_value = get_mock_factsheet()
    mock_writer = MagicMock()

    with patch('agent.clean.get_stream_writer', return_value=mock_writer), \
         patch('agent.clean.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.clean.pick_llm', return_value=MagicMock()):
        result = await mock_clean._load_project_node(state)

    assert "input_" in result
    assert isinstance(result["input_"], ProjectData)


@pytest.mark.asyncio
async def test_load_project_node_missing_project_raises(mock_clean):
    """_load_project_node raises ValueError when project not found."""
    query = get_mock_cleanup_request(["events"])
    state = PipelineState(query=query)

    mock_clean.conversation_manager.load_project.return_value = None
    mock_writer = MagicMock()

    with patch('agent.clean.get_stream_writer', return_value=mock_writer), \
         patch('agent.clean.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.clean.pick_llm', return_value=MagicMock()), \
         pytest.raises(ValueError):
        await mock_clean._load_project_node(state)


@pytest.mark.asyncio
async def test_load_project_node_invalid_type_raises(mock_clean):
    """_load_project_node raises an error when load_factsheet returns wrong type."""
    query = get_mock_cleanup_request(["events"])
    state = PipelineState(query=query)

    mock_clean.conversation_manager.load_factsheet.return_value = {"invalid": "dict"}
    mock_writer = MagicMock()

    with patch('agent.clean.get_stream_writer', return_value=mock_writer), \
         patch('agent.clean.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.clean.pick_llm', return_value=MagicMock()), \
         pytest.raises(Exception):
        await mock_clean._load_project_node(state)


# ============================================
#           CLEAN ELEMENTS NODE
# ============================================

@pytest.mark.asyncio
async def test_clean_elements_node(mock_clean):
    """_clean_elements_node calls clean_elements and updates factsheet."""
    query = get_mock_cleanup_request(["events"])
    factsheet = get_mock_factsheet()
    project_data = ProjectData(factsheet=factsheet, attachments=[], emails=[])
    state = PipelineState(query=query, input_=project_data)

    cleaned_events = [
        {
            "event_id": "event-cleaned-001",
            "event_name": "ContractSigned",
            "event_start_date": "2023-08-25",
            "description": "Cleaned event",
            "significance": "high",
            "disputed": False,
            "category": "transaction",
        }
    ]
    mock_clean.context_manager.clean_elements = AsyncMock(return_value={"events": cleaned_events})
    mock_writer = MagicMock()

    with patch('agent.clean.get_stream_writer', return_value=mock_writer), \
         patch('agent.clean.get_config', return_value=MOCK_THREAD_CONFIG), \
         patch('agent.clean.pick_llm', return_value=MagicMock()):
        result = await mock_clean._clean_elements_node(state)

    assert "input_" in result
    assert isinstance(result["input_"], ProjectData)
    assert len(result["input_"].factsheet.events) == len(cleaned_events)
    assert all(isinstance(e, Event) for e in result["input_"].factsheet.events)
    mock_clean.context_manager.clean_elements.assert_called_once_with(["events"], project_data)


# ============================================
#           CLEAN METADATA NODE
# ============================================

@pytest.mark.asyncio
async def test_clean_metadata_node(mock_clean):
    """_clean_metadata_node calls clean_all_metadata and updates factsheet."""
    query = get_mock_cleanup_request([])
    factsheet = get_mock_factsheet()
    project_data = ProjectData(factsheet=factsheet, attachments=[], emails=[])
    state = PipelineState(query=query, input_=project_data)

    am = AsyncMock(return_value={"title": "Cleaned Title", "background": "Cleaned background text"})
    mock_writer = MagicMock()

    with patch.object(mock_clean.context_manager, 'clean_metadata', new=am, create=True), \
         patch('agent.clean.get_stream_writer', return_value=mock_writer), \
         patch('agent.clean.get_config', return_value=MOCK_THREAD_CONFIG):
        result = await mock_clean._clean_metadata_node(state)

    assert "input_" in result
    assert result["input_"].factsheet.title == "Cleaned Title"
    assert result["input_"].factsheet.background == "Cleaned background text"


# ============================================
#           SAVE ELEMENTS NODE
# ============================================

@pytest.mark.asyncio
async def test_save_elements_node(mock_clean):
    """_save_elements_node replaces elements in DB and writes result event."""
    query = get_mock_cleanup_request(["events"])
    factsheet = get_mock_factsheet()
    project_data = ProjectData(factsheet=factsheet, attachments=[], emails=[])
    state = PipelineState(query=query, input_=project_data)

    mock_clean.conversation_manager.upsert_replace_project_element = MagicMock()
    writer_calls = []
    mock_writer = MagicMock(side_effect=lambda x: writer_calls.append(x))

    with patch('agent.clean.get_stream_writer', return_value=mock_writer):
        await mock_clean._save_elements_node(state)

    mock_clean.conversation_manager.upsert_replace_project_element.assert_called()
    result_calls = [c for c in writer_calls if isinstance(c, dict) and c.get("type") == "result"]
    assert len(result_calls) == 1
    assert result_calls[0]["data"]["success"] is True


# ============================================
#           SAVE METADATA NODE
# ============================================

@pytest.mark.asyncio
async def test_save_metadata_node(mock_clean):
    """_save_metadata_node saves title and background, writes result event."""
    query = get_mock_cleanup_request([])
    factsheet = get_mock_factsheet()
    project_data = ProjectData(factsheet=factsheet, attachments=[], emails=[])
    state = PipelineState(query=query, input_=project_data)

    mock_clean.conversation_manager.upsert_project = MagicMock()
    writer_calls = []
    mock_writer = MagicMock(side_effect=lambda x: writer_calls.append(x))

    with patch('agent.clean.get_stream_writer', return_value=mock_writer):
        await mock_clean._save_metadata_node(state)

    assert mock_clean.conversation_manager.upsert_project.call_count == 2
    result_calls = [c for c in writer_calls if isinstance(c, dict) and c.get("type") == "result"]
    assert len(result_calls) == 1
    assert result_calls[0]["data"]["success"] is True
