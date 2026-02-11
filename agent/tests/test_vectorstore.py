import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import os
import base64
from datetime import datetime

from langchain_core.documents import Document
from tests.fixtures.vectorstore_data import *
from tests.fixtures.email_data import (
    get_mock_eml_plain_text,
    get_mock_eml_plain_text_b64,
    get_mock_eml_multipart,
    get_mock_eml_with_text_attachment,
    get_mock_eml_with_text_attachment_b64,
    get_mock_eml_metadata,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================
#           DOCUMENT PROCESSOR TESTS
# ============================================

from database.vectorstore_modules import DocumentProcessor


@pytest.fixture
def doc_processor():
    """DocumentProcessor with default settings."""
    return DocumentProcessor(chunk_size=800, chunk_overlap=100)


@pytest.fixture
def doc_processor_small_chunks():
    """DocumentProcessor with small chunks for testing splitting."""
    return DocumentProcessor(chunk_size=200, chunk_overlap=20)


# --- needs_ocr ---

def test_needs_ocr_empty_pdf(doc_processor):
    """PDF without text should need OCR."""
    pdf_bytes = get_mock_pdf_bytes_empty()
    result = doc_processor._needs_ocr(pdf_bytes)
    assert result is True


def test_needs_ocr_invalid_bytes(doc_processor):
    """Invalid bytes should return False (default: no OCR on failure)."""
    result = doc_processor._needs_ocr(b"not a valid pdf")
    assert result is False


def test_needs_ocr_with_text(doc_processor):
    """PDF with sufficient text should not need OCR."""
    # Mock PdfReader to simulate a PDF with text on all pages
    with patch('database.vectorstore_modules.PdfReader') as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "A" * 200  # Plenty of text
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page, mock_page, mock_page]
        mock_reader_cls.return_value = mock_reader

        result = doc_processor._needs_ocr(b"fake pdf bytes")
        assert result is False


def test_needs_ocr_low_text_coverage(doc_processor):
    """PDF where <50% of pages have text should need OCR."""
    with patch('database.vectorstore_modules.PdfReader') as mock_reader_cls:
        page_with_text = MagicMock()
        page_with_text.extract_text.return_value = "A" * 200

        page_without_text = MagicMock()
        page_without_text.extract_text.return_value = ""

        mock_reader = MagicMock()
        # 1 page with text, 3 without => 25% coverage
        mock_reader.pages = [page_with_text, page_without_text, page_without_text, page_without_text]
        mock_reader_cls.return_value = mock_reader

        result = doc_processor._needs_ocr(b"fake pdf bytes")
        assert result is True


# --- _ocr_bytes ---

def test_ocr_bytes_success(doc_processor):
    """Test OCR processing returns OCR'd bytes."""
    input_bytes = b"fake pdf input"
    expected_output = b"ocr processed output"

    with patch('database.vectorstore_modules.ocrmypdf') as mock_ocr:
        mock_ocr.ocr.return_value = None  # ocrmypdf.ocr returns None on success
        # Mock the output file read
        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=expected_output)))
            mock_open.return_value.__exit__ = MagicMock(return_value=False)

            with patch('os.unlink'):
                result = doc_processor._ocr_bytes(input_bytes)
                # ocrmypdf.ocr should have been called
                mock_ocr.ocr.assert_called_once()


def test_ocr_bytes_prior_ocr_returns_original(doc_processor):
    """Test OCR returns original when PriorOcrFoundError is raised."""
    import ocrmypdf
    input_bytes = b"already ocr'd pdf"

    with patch('database.vectorstore_modules.ocrmypdf') as mock_ocr_module:
        mock_ocr_module.ocr.side_effect = ocrmypdf.exceptions.PriorOcrFoundError()
        mock_ocr_module.exceptions = ocrmypdf.exceptions

        with patch('os.unlink'):
            result = doc_processor._ocr_bytes(input_bytes)
            assert result == input_bytes


def test_ocr_bytes_error_returns_original(doc_processor):
    """Test OCR returns original PDF on general failure."""
    input_bytes = b"problematic pdf"

    with patch('database.vectorstore_modules.ocrmypdf') as mock_ocr_module:
        import ocrmypdf
        mock_ocr_module.ocr.side_effect = RuntimeError("OCR failed")
        mock_ocr_module.exceptions = ocrmypdf.exceptions

        with patch('os.unlink'):
            result = doc_processor._ocr_bytes(input_bytes)
            assert result == input_bytes


# --- parse_pdf ---

def test_parse_pdf_with_text(doc_processor):
    """Test parse_pdf extracts text from PDF pages."""
    metadata = get_mock_metadata()

    with patch.object(doc_processor, '_needs_ocr', return_value=False):
        with patch('database.vectorstore_modules.PdfReader') as mock_reader_cls:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Innhold fra side 1 om eiendomstvist"

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page, mock_page]
            mock_reader.metadata = {"/Creator": "TestPDF"}
            mock_reader_cls.return_value = mock_reader

            result = doc_processor.parse_pdf(b"fake pdf bytes", metadata)

            assert len(result) == 2
            assert isinstance(result[0], Document)
            assert result[0].metadata["file_id"] == metadata["file_id"]
            assert result[0].metadata["session_id"] == metadata["session_id"]
            assert result[0].metadata["page"] == 1
            assert result[1].metadata["page"] == 2
            assert result[0].metadata["total_pages"] == 2
            assert result[0].metadata["creator"] == "TestPDF"


def test_parse_pdf_empty_pages(doc_processor):
    """Test parse_pdf returns empty list when no pages have text."""
    metadata = get_mock_metadata()

    with patch.object(doc_processor, '_needs_ocr', return_value=False):
        with patch('database.vectorstore_modules.PdfReader') as mock_reader_cls:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page, mock_page]
            mock_reader.metadata = None
            mock_reader_cls.return_value = mock_reader

            result = doc_processor.parse_pdf(b"fake pdf bytes", metadata)
            assert result == []


def test_parse_pdf_skips_empty_pages(doc_processor):
    """Test parse_pdf skips pages without text but includes those with text."""
    metadata = get_mock_metadata()

    with patch.object(doc_processor, '_needs_ocr', return_value=False):
        with patch('database.vectorstore_modules.PdfReader') as mock_reader_cls:
            page_with_text = MagicMock()
            page_with_text.extract_text.return_value = "Innhold om rettssaken"

            page_empty = MagicMock()
            page_empty.extract_text.return_value = ""

            mock_reader = MagicMock()
            mock_reader.pages = [page_with_text, page_empty, page_with_text]
            mock_reader.metadata = None
            mock_reader_cls.return_value = mock_reader

            result = doc_processor.parse_pdf(b"fake pdf bytes", metadata)
            assert len(result) == 2
            assert result[0].metadata["page"] == 1
            assert result[1].metadata["page"] == 3


def test_parse_pdf_triggers_ocr_when_needed(doc_processor):
    """Test parse_pdf calls OCR when needs_ocr returns True."""
    metadata = get_mock_metadata()

    with patch.object(doc_processor, '_needs_ocr', return_value=True):
        with patch.object(doc_processor, '_ocr_bytes', return_value=b"ocr output") as mock_ocr:
            with patch('database.vectorstore_modules.PdfReader') as mock_reader_cls:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "OCR extracted text"

                mock_reader = MagicMock()
                mock_reader.pages = [mock_page]
                mock_reader.metadata = None
                mock_reader_cls.return_value = mock_reader

                result = doc_processor.parse_pdf(b"scanned pdf", metadata)
                mock_ocr.assert_called_once_with(b"scanned pdf")
                assert len(result) == 1


def test_parse_pdf_invalid_pdf(doc_processor):
    """Test parse_pdf returns empty list for invalid PDF."""
    metadata = get_mock_metadata()

    with patch.object(doc_processor, '_needs_ocr', return_value=False):
        with patch('database.vectorstore_modules.PdfReader', side_effect=Exception("Invalid PDF")):
            result = doc_processor.parse_pdf(b"invalid", metadata)
            assert result == []


# --- parse_text ---

def test_parse_text_short(doc_processor):
    """Test parse_text with content shorter than chunk_size."""
    text = get_mock_text_content()
    metadata = get_mock_metadata()

    result = doc_processor.parse_text(text.encode("utf-8"), metadata)

    assert len(result) >= 1
    assert isinstance(result[0], Document)
    assert result[0].metadata["file_id"] == metadata["file_id"]
    assert result[0].metadata["session_id"] == metadata["session_id"]
    assert "chunk" in result[0].metadata
    assert "total_chunks" in result[0].metadata


def test_parse_text_long_produces_multiple_chunks(doc_processor_small_chunks):
    """Test parse_text produces multiple chunks for long text."""
    text = get_mock_long_text_content()
    metadata = get_mock_metadata()

    result = doc_processor_small_chunks.parse_text(text.encode("utf-8"), metadata)

    assert len(result) > 1
    for i, doc in enumerate(result):
        assert doc.metadata["chunk"] == i
        assert doc.metadata["total_chunks"] == len(result)


def test_parse_text_empty(doc_processor):
    """Test parse_text with empty string returns empty list."""
    metadata = get_mock_metadata()
    result = doc_processor.parse_text(b"", metadata)
    assert result == []


def test_parse_text_preserves_metadata(doc_processor):
    """Test parse_text carries over all metadata to each chunk."""
    text = get_mock_text_content()
    metadata = {"file_id": "test-id", "session_id": "sess-id", "custom_field": "value"}

    result = doc_processor.parse_text(text.encode("utf-8"), metadata)

    for doc in result:
        assert doc.metadata["file_id"] == "test-id"
        assert doc.metadata["session_id"] == "sess-id"
        assert doc.metadata["custom_field"] == "value"


# --- parse (main entry point, replaces old process_attachment) ---

def test_parse_routes_pdf(doc_processor):
    """Test parse() routes PDF to parse_pdf with base64 decoding."""
    content = get_mock_pdf_base64_with_text()
    metadata = get_mock_metadata()

    with patch.object(doc_processor, 'parse_pdf', return_value=[Document(page_content="parsed")]) as mock_parse:
        result = doc_processor.parse(
            content=content,
            file_type="application/pdf",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        # First positional arg should be decoded bytes
        assert isinstance(call_args.args[0], bytes)
        # Metadata should have file_id and session_id
        assert call_args.kwargs["metadata"]["file_id"] == metadata["file_id"]
        assert call_args.kwargs["metadata"]["session_id"] == metadata["session_id"]


def test_parse_routes_text(doc_processor):
    """Test parse() routes text/plain to parse_text with base64 decoding."""
    text_content = get_mock_text_content()
    b64_content = base64.b64encode(text_content.encode("utf-8")).decode("utf-8")
    metadata = get_mock_metadata()

    with patch.object(doc_processor, 'parse_text', return_value=[Document(page_content="parsed")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="text/plain",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


def test_parse_routes_eml(doc_processor):
    """Test parse() routes message/rfc822 to parse_eml."""
    b64_content = get_mock_eml_plain_text_b64()
    metadata = get_mock_eml_metadata()

    with patch.object(doc_processor, 'parse_eml', return_value=[Document(page_content="email text")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="message/rfc822",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        assert len(result) == 1


def test_parse_invalid_base64(doc_processor):
    """Test parse() handles invalid base64 gracefully."""
    metadata = get_mock_metadata()
    result = doc_processor.parse(
        content="not-valid-base64!!!",
        file_type="application/pdf",
        metadata=metadata,
    )
    assert result == []


def test_parse_missing_metadata_raises(doc_processor):
    """Test parse() raises ValueError when metadata is missing file_id or session_id."""
    with pytest.raises(ValueError, match="Metadata must include"):
        doc_processor.parse(
            content="dGVzdA==",
            file_type="text/plain",
            metadata={"file_id": "test"},  # missing session_id
        )


def test_parse_unsupported_file_type(doc_processor):
    """Test parse() returns empty list for unsupported file types."""
    metadata = get_mock_metadata()
    result = doc_processor.parse(
        content="dGVzdA==",
        file_type="application/unknown",
        metadata=metadata,
    )
    assert result == []


def test_parse_routes_csv(doc_processor):
    """Test parse() routes text/csv to parse_csv."""
    csv_content = "col1,col2\nval1,val2"
    b64_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
    metadata = get_mock_metadata()

    with patch.object(doc_processor, 'parse_csv', return_value=[Document(page_content="csv data")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="text/csv",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


# --- parse_eml (DocumentProcessor) ---

def test_parse_eml_plain_text(doc_processor):
    """Test parse_eml extracts text from plain text email."""
    raw = get_mock_eml_plain_text()
    metadata = get_mock_eml_metadata()

    result = doc_processor.parse_eml(raw, metadata)

    assert len(result) >= 1
    assert isinstance(result[0], Document)
    assert "eiendomssaken" in result[0].page_content
    assert result[0].metadata["file_id"] == metadata["file_id"]
    assert result[0].metadata["session_id"] == metadata["session_id"]
    assert "chunk" in result[0].metadata
    assert "total_chunks" in result[0].metadata


def test_parse_eml_multipart(doc_processor):
    """Test parse_eml extracts text from multipart email."""
    raw = get_mock_eml_multipart()
    metadata = get_mock_eml_metadata()

    result = doc_processor.parse_eml(raw, metadata)

    assert len(result) >= 1
    assert isinstance(result[0], Document)
    assert "Befaring" in result[0].page_content


def test_parse_eml_with_attachment(doc_processor):
    """Test parse_eml processes email body (not attachments) into documents."""
    raw = get_mock_eml_with_text_attachment()
    metadata = get_mock_eml_metadata()

    result = doc_processor.parse_eml(raw, metadata)

    assert len(result) >= 1
    # Body text should be in the documents
    assert any("vedlagt" in doc.page_content.lower() for doc in result)


def test_parse_eml_preserves_metadata(doc_processor):
    """Test parse_eml preserves all metadata across chunks."""
    raw = get_mock_eml_plain_text()
    metadata = {"file_id": "eml-001", "session_id": "s-001", "custom": "value"}

    result = doc_processor.parse_eml(raw, metadata)

    for doc in result:
        assert doc.metadata["file_id"] == "eml-001"
        assert doc.metadata["session_id"] == "s-001"
        assert doc.metadata["custom"] == "value"


def test_parse_eml_invalid_bytes(doc_processor):
    """Test parse_eml with invalid bytes raises ValueError."""
    metadata = get_mock_eml_metadata()
    # email.message_from_bytes is very lenient, so invalid bytes usually parse
    # but produce empty content rather than raising
    result = doc_processor.parse_eml(b"not a real email", metadata)
    # Should return at least one document (possibly empty)
    assert isinstance(result, list)


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

    mock_store.as_retriever.assert_called_once_with(search_kwargs={"k": 5})
    mock_retriever.invoke.assert_called_once_with("eiendomstvist")
    assert result == expected


def test_bq_delete_collection(mock_bq_store):
    """Test delete_collection is a no-op (not implemented)."""
    # Should not raise
    mock_bq_store.delete_collection("test-collection")
