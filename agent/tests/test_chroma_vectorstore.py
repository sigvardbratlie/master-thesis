import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import os

from tests.fixtures.vectorstore_data import *


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================
#           CHROMA VECTOR STORE TESTS
# ============================================

from database.vectorstore_modules import ChromaVectorStore

@pytest.fixture
def mock_chroma_store():
    """ChromaVectorStore with mocked embedding and Chroma backend."""
    with patch('database.vectorstore_modules.GoogleGenerativeAIEmbeddings') as mock_embed_cls:
        mock_embedding = MagicMock()
        mock_embed_cls.return_value = mock_embedding

        store = ChromaVectorStore(embedding_model="google_gemini-embedding-001")
        yield store


def test_chroma_init_google_embedding(mock_chroma_store):
    """Test ChromaVectorStore initializes with Google embedding."""
    assert mock_chroma_store.embedding is not None
    assert mock_chroma_store.embedding_model == "google_gemini-embedding-001"
    assert mock_chroma_store._collections == {}


def test_chroma_init_unknown_embedding():
    """Test ChromaVectorStore falls back to default for unknown embedding prefix."""
    with patch('database.vectorstore_modules.GoogleGenerativeAIEmbeddings') as mock_embed_cls:
        store = ChromaVectorStore(embedding_model="unknown_model")
        # Should still create embeddings with fallback model
        mock_embed_cls.assert_called_with(model="gemini-embedding-001")


def test_chroma_get_collection_creates_new(mock_chroma_store):
    """Test _get_collection creates a new Chroma collection."""
    with patch('database.vectorstore_modules.Chroma') as mock_chroma_cls:
        mock_collection = MagicMock()
        mock_chroma_cls.return_value = mock_collection

        result = mock_chroma_store._get_collection("test-session-id")

        mock_chroma_cls.assert_called_once_with(
            collection_name="test-session-id",
            embedding_function=mock_chroma_store.embedding,
        )
        assert result == mock_collection
        assert "test-session-id" in mock_chroma_store._collections


def test_chroma_get_collection_reuses_existing(mock_chroma_store):
    """Test _get_collection returns cached collection."""
    mock_collection = MagicMock()
    mock_chroma_store._collections["test-session-id"] = mock_collection

    result = mock_chroma_store._get_collection("test-session-id")
    assert result == mock_collection


def test_chroma_add_documents(mock_chroma_store):
    """Test add_documents adds to the correct collection."""
    docs = get_mock_documents()
    mock_collection = MagicMock()
    mock_chroma_store._collections["test-session"] = mock_collection

    mock_chroma_store.add_documents(docs, collection_id="test-session")

    mock_collection.add_documents.assert_called_once_with(docs)


def test_chroma_add_documents_error(mock_chroma_store):
    """Test add_documents handles errors gracefully."""
    docs = get_mock_documents()
    mock_collection = MagicMock()
    mock_collection.add_documents.side_effect = Exception("Embedding failed")
    mock_chroma_store._collections["test-session"] = mock_collection

    # Should not raise
    mock_chroma_store.add_documents(docs, collection_id="test-session")


def test_chroma_query(mock_chroma_store):
    """Test query retrieves documents from collection."""
    expected = get_mock_query_results()
    mock_collection = MagicMock()
    mock_retriever = MagicMock()
    mock_retriever.invoke.return_value = expected
    mock_collection.as_retriever.return_value = mock_retriever
    mock_chroma_store._collections["test-session"] = mock_collection

    result = mock_chroma_store.query("eiendomstvist", collection_id="test-session", k=3)

    mock_collection.as_retriever.assert_called_once_with(search_kwargs={"k": 3})
    mock_retriever.invoke.assert_called_once_with("eiendomstvist")
    assert result == expected


def test_chroma_delete_collection(mock_chroma_store):
    """Test delete_collection removes from cache."""
    mock_chroma_store._collections["test-session"] = MagicMock()

    mock_chroma_store.delete_collection("test-session")
    assert "test-session" not in mock_chroma_store._collections


def test_chroma_delete_collection_nonexistent(mock_chroma_store):
    """Test delete_collection handles non-existent collection."""
    # Should not raise
    mock_chroma_store.delete_collection("nonexistent")


def test_chroma_add_embeddings_meta(mock_chroma_store):
    """Test add_embeddings_meta adds metadata to document."""
    doc = Document(page_content="test", metadata={"file_id": "f1"})

    mock_chroma_store.add_embeddings_meta(doc)

    assert "added_at" in doc.metadata
    assert doc.metadata["embedding_model"] == "google_gemini-embedding-001"
    assert doc.metadata["file_id"] == "f1"  # Original metadata preserved


def test_chroma_add_embeddings_meta_empty_metadata(mock_chroma_store):
    """Test add_embeddings_meta works when document has empty metadata."""
    doc = Document(page_content="test", metadata={})

    mock_chroma_store.add_embeddings_meta(doc)

    assert "added_at" in doc.metadata
    assert doc.metadata["embedding_model"] == "google_gemini-embedding-001"


def test_chroma_get_all(mock_chroma_store):
    """Test get_all retrieves all documents from collection."""
    mock_data = get_mock_chroma_get_all_response()
    mock_collection = MagicMock()
    mock_collection._collection.get.return_value = mock_data
    mock_chroma_store._collections["test-session"] = mock_collection

    result = mock_chroma_store.get_all("test-session")

    mock_collection._collection.get.assert_called_once_with(
        include=["documents", "metadatas"]
    )
    assert len(result) == 3
    assert isinstance(result[0], Document)
    assert result[0].page_content == mock_data["documents"][0]
    assert result[0].metadata == mock_data["metadatas"][0]
    assert result[0].id == mock_data["ids"][0]

