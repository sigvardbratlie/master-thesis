
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import os

from tests.fixtures.vectorstore_data import *


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))



# ============================================
#           BQ VECTOR STORE TESTS
# ============================================

from database.vectorstore_modules import BQVectorStore


@pytest.fixture
def mock_bq_store():
    """BQVectorStore with mocked embedding and BigQuery backend."""
    with patch('database.vectorstore_modules.GoogleGenerativeAIEmbeddings') as mock_embed_cls:
        mock_embedding = MagicMock()
        mock_embed_cls.return_value = mock_embedding

        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            store = BQVectorStore(
                dataset="test_dataset",
                region="europe-north2",
                embedding_model="google_gemini-embedding-001",
            )
            yield store


def test_bq_init(mock_bq_store):
    """Test BQVectorStore initializes correctly."""
    assert mock_bq_store.project_id == "test-project"
    assert mock_bq_store.dataset == "test_dataset"
    assert mock_bq_store.region == "europe-north2"
    assert mock_bq_store.embedding_model == "google_gemini-embedding-001"
    assert mock_bq_store._stores == {}


def test_bq_init_unknown_embedding():
    """Test BQVectorStore falls back to default for unknown embedding prefix."""
    with patch('database.vectorstore_modules.GoogleGenerativeAIEmbeddings') as mock_embed_cls:
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            store = BQVectorStore(embedding_model="unknown_model")
            mock_embed_cls.assert_called_with(model="gemini-embedding-001")


def test_bq_get_store_creates_new(mock_bq_store):
    """Test _get_store creates a new BigQueryVectorStore."""
    with patch('database.vectorstore_modules.BigQueryVectorStore') as mock_bq_cls:
        mock_store = MagicMock()
        mock_bq_cls.return_value = mock_store

        result = mock_bq_store._get_store("test-collection")

        mock_bq_cls.assert_called_once_with(
            project_id="test-project",
            dataset_name="test_dataset",
            table_name="test-collection",
            location="europe-north2",
            embedding=mock_bq_store.embedding,
        )
        assert result == mock_store
        assert "test-collection" in mock_bq_store._stores


def test_bq_get_store_reuses_existing(mock_bq_store):
    """Test _get_store returns cached store."""
    mock_store = MagicMock()
    mock_bq_store._stores["test-collection"] = mock_store

    result = mock_bq_store._get_store("test-collection")
    assert result == mock_store


def test_bq_add_documents(mock_bq_store):
    """Test add_documents adds to the correct store."""
    docs = get_mock_documents()
    mock_store = MagicMock()
    mock_bq_store._stores["test-collection"] = mock_store

    mock_bq_store.add_documents(docs, collection_id="test-collection")

    mock_store.add_documents.assert_called_once_with(docs)


def test_bq_add_documents_with_meta(mock_bq_store):
    """Test add_documents adds embedding metadata when add_embeddings_meta=True."""
    docs = get_mock_documents()
    mock_store = MagicMock()
    mock_bq_store._stores["test-collection"] = mock_store

    with patch.object(mock_bq_store, 'add_embeddings_meta') as mock_add_meta:
        mock_bq_store.add_documents(docs, collection_id="test-collection", add_embeddings_meta=True)
        assert mock_add_meta.call_count == len(docs)


def test_bq_add_documents_without_meta(mock_bq_store):
    """Test add_documents skips metadata when add_embeddings_meta=False."""
    docs = get_mock_documents()
    mock_store = MagicMock()
    mock_bq_store._stores["test-collection"] = mock_store

    with patch.object(mock_bq_store, 'add_embeddings_meta') as mock_add_meta:
        mock_bq_store.add_documents(docs, collection_id="test-collection", add_embeddings_meta=False)
        mock_add_meta.assert_not_called()


def test_bq_add_embeddings_meta(mock_bq_store):
    """Test add_embeddings_meta adds embedding model to metadata."""
    doc = Document(page_content="test", metadata={"file_id": "f1"})

    mock_bq_store.add_embeddings_meta(doc)

    assert doc.metadata["embedding_model"] == "google_gemini-embedding-001"
    assert doc.metadata["file_id"] == "f1"


def test_bq_query(mock_bq_store):
    """Test query retrieves documents from BQ store."""
    expected = get_mock_query_results()
    mock_store = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = expected
    mock_store.as_retriever.return_value = mock_retriever
    mock_bq_store._stores["test-collection"] = mock_store

    result = mock_bq_store.query("eiendomstvist", collection_id="test-collection", k=5)

    mock_store.as_retriever.assert_called_once_with(search_kwargs={"k": 5}, filter = {})
    mock_retriever.invoke.assert_called_once_with("eiendomstvist")
    assert result == expected


def test_bq_delete_collection(mock_bq_store):
    """Test delete_collection is a no-op (not implemented)."""
    # Should not raise
    mock_bq_store.delete_collection("test-collection")
