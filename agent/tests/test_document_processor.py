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

from documents import DocumentProcessor, PDFHandler, TextHandler, EmailHandler, PptxHandler, DocxHandler


@pytest.fixture
def pdf_handler():
    """PDFHandler instance."""
    return PDFHandler()


@pytest.fixture
def text_handler():
    """TextHandler with default splitter settings."""
    return TextHandler()


@pytest.fixture
def text_handler_small_chunks():
    """TextHandler with small chunks for testing splitting."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    handler = TextHandler()
    handler.splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)
    return handler


@pytest.fixture
def email_handler():
    """EmailHandler instance."""
    return EmailHandler()


@pytest.fixture
def docx_handler():
    """DocxHandler instance."""
    return DocxHandler()


@pytest.fixture
def pptx_handler():
    """PptxHandler instance."""
    return PptxHandler()


@pytest.fixture
def doc_processor():
    """DocumentProcessor instance."""
    return DocumentProcessor()


# ============================================
#           PDF HANDLER TESTS
# ============================================

# --- needs_ocr ---

def test_needs_ocr_empty_pdf(pdf_handler):
    """PDF without text should need OCR."""
    pdf_bytes = get_mock_pdf_bytes_empty()
    result = pdf_handler._needs_ocr(pdf_bytes)
    assert result is True


def test_needs_ocr_invalid_bytes(pdf_handler):
    """Invalid bytes should return False (default: no OCR on failure)."""
    result = pdf_handler._needs_ocr(b"not a valid pdf")
    assert result is False


def test_needs_ocr_with_text(pdf_handler):
    """PDF with sufficient text should not need OCR."""
    with patch('documents.document_modules.PdfReader') as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "A" * 200
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page, mock_page, mock_page]
        mock_reader_cls.return_value = mock_reader

        result = pdf_handler._needs_ocr(b"fake pdf bytes")
        assert result is False


def test_needs_ocr_low_text_coverage(pdf_handler):
    """PDF where <50% of pages have text should need OCR."""
    with patch('documents.document_modules.PdfReader') as mock_reader_cls:
        page_with_text = MagicMock()
        page_with_text.extract_text.return_value = "A" * 200

        page_without_text = MagicMock()
        page_without_text.extract_text.return_value = ""

        mock_reader = MagicMock()
        mock_reader.pages = [page_with_text, page_without_text, page_without_text, page_without_text]
        mock_reader_cls.return_value = mock_reader

        result = pdf_handler._needs_ocr(b"fake pdf bytes")
        assert result is True


# --- _ocr_bytes ---

def test_ocr_bytes_success(pdf_handler):
    """Test OCR processing returns OCR'd bytes."""
    input_bytes = b"fake pdf input"
    expected_output = b"ocr processed output"

    with patch('documents.document_modules.ocrmypdf') as mock_ocr:
        mock_ocr.ocr.return_value = None
        with patch('builtins.open', MagicMock()) as mock_open:
            mock_open.return_value.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value=expected_output)))
            mock_open.return_value.__exit__ = MagicMock(return_value=False)

            with patch('os.unlink'):
                result = pdf_handler._ocr_bytes(input_bytes)
                mock_ocr.ocr.assert_called_once()


def test_ocr_bytes_prior_ocr_returns_original(pdf_handler):
    """Test OCR returns original when PriorOcrFoundError is raised."""
    import ocrmypdf
    input_bytes = b"already ocr'd pdf"

    with patch('documents.document_modules.ocrmypdf') as mock_ocr_module:
        mock_ocr_module.ocr.side_effect = ocrmypdf.exceptions.PriorOcrFoundError()
        mock_ocr_module.exceptions = ocrmypdf.exceptions

        with patch('os.unlink'):
            result = pdf_handler._ocr_bytes(input_bytes)
            assert result == input_bytes


def test_ocr_bytes_error_returns_original(pdf_handler):
    """Test OCR returns original PDF on general failure."""
    input_bytes = b"problematic pdf"

    with patch('documents.document_modules.ocrmypdf') as mock_ocr_module:
        import ocrmypdf
        mock_ocr_module.ocr.side_effect = RuntimeError("OCR failed")
        mock_ocr_module.exceptions = ocrmypdf.exceptions

        with patch('os.unlink'):
            result = pdf_handler._ocr_bytes(input_bytes)
            assert result == input_bytes


# --- parse_pdf_to_docs ---

def test_parse_pdf_to_docs_with_text(pdf_handler):
    """Test parse_pdf_to_docs extracts text from PDF pages."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch('documents.document_modules.PdfReader') as mock_reader_cls:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Innhold fra side 1 om eiendomstvist"

            mock_reader = MagicMock()
            metamock = MagicMock()
            metamock.title = "TestPDF"
            metamock.subject = "TestPDF"
            metamock.author = "TestAuthor"
            metamock.created = datetime(2024, 1, 15)
            metamock.modified = datetime(2024, 1, 15)
            metamock.creation_date = datetime(2024, 1, 15)
            metamock.modification_date = datetime(2024, 1, 15)
            metamock.creator = "TestCreator"
            metamock.producer = "TestProducer"
            metamock.get = MagicMock(return_value=None)
            metamock.comments = None
            metamock.language = None
            mock_reader.pages = [mock_page, mock_page]
            mock_reader.metadata = metamock
            mock_reader_cls.return_value = mock_reader

            result = pdf_handler.parse_pdf_to_docs(b"fake pdf bytes", metadata)

            assert len(result) == 2
            assert isinstance(result[0], Document)
            assert result[0].metadata["file_id"] == metadata["file_id"]
            assert result[0].metadata["session_id"] == metadata["session_id"]
            assert result[0].metadata["chunk"] == 1
            assert result[1].metadata["chunk"] == 2
            assert result[0].metadata["total_chunks"] == 2
            assert result[0].metadata["creator"] == "TestCreator"


def test_parse_pdf_to_docs_empty_pages(pdf_handler):
    """Test parse_pdf_to_docs returns empty list when no pages have text."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch('documents.document_modules.PdfReader') as mock_reader_cls:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = ""

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page, mock_page]
            mock_reader.metadata = None
            mock_reader_cls.return_value = mock_reader

            result = pdf_handler.parse_pdf_to_docs(b"fake pdf bytes", metadata)
            assert result == []


def test_parse_pdf_to_docs_skips_empty_pages(pdf_handler):
    """Test parse_pdf_to_docs skips pages without text but includes those with text."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch('documents.document_modules.PdfReader') as mock_reader_cls:
            page_with_text = MagicMock()
            page_with_text.extract_text.return_value = "Innhold om rettssaken"

            page_empty = MagicMock()
            page_empty.extract_text.return_value = ""

            mock_reader = MagicMock()
            mock_reader.pages = [page_with_text, page_empty, page_with_text]
            mock_reader.metadata = None
            mock_reader_cls.return_value = mock_reader

            result = pdf_handler.parse_pdf_to_docs(b"fake pdf bytes", metadata)
            assert len(result) == 2
            assert result[0].metadata["chunk"] == 1
            assert result[1].metadata["chunk"] == 3


def test_parse_pdf_to_docs_triggers_ocr_when_needed(pdf_handler):
    """Test parse_pdf_to_docs calls OCR when needs_ocr returns True."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=True):
        with patch.object(pdf_handler, '_ocr_bytes', return_value=b"ocr output") as mock_ocr:
            with patch('documents.document_modules.PdfReader') as mock_reader_cls:
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "OCR extracted text"

                mock_reader = MagicMock()
                mock_reader.pages = [mock_page]
                mock_reader.metadata = None
                mock_reader_cls.return_value = mock_reader

                result = pdf_handler.parse_pdf_to_docs(b"scanned pdf", metadata)
                mock_ocr.assert_called_once_with(b"scanned pdf")
                assert len(result) == 1


def test_parse_pdf_to_docs_invalid_pdf(pdf_handler):
    """Test parse_pdf_to_docs returns empty list for invalid PDF."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch('documents.document_modules.PdfReader', side_effect=Exception("Invalid PDF")):
            result = pdf_handler.parse_pdf_to_docs(b"invalid", metadata)
            assert result == []


# ============================================
#           TEXT HANDLER TESTS
# ============================================

# --- parse_text_to_docs ---

def test_parse_text_to_docs_short(text_handler):
    """Test parse_text_to_docs with content shorter than chunk_size."""
    text = get_mock_text_content()
    metadata = get_mock_metadata()

    result = text_handler.parse_text_to_docs(text.encode("utf-8"), metadata)

    assert len(result) >= 1
    assert isinstance(result[0], Document)
    assert result[0].metadata["file_id"] == metadata["file_id"]
    assert result[0].metadata["session_id"] == metadata["session_id"]
    assert "chunk" in result[0].metadata
    assert "total_chunks" in result[0].metadata


def test_parse_text_to_docs_long_produces_multiple_chunks(text_handler_small_chunks):
    """Test parse_text_to_docs produces multiple chunks for long text."""
    text = get_mock_long_text_content()
    metadata = get_mock_metadata()

    result = text_handler_small_chunks.parse_text_to_docs(text.encode("utf-8"), metadata)

    assert len(result) > 1
    for i, doc in enumerate(result):
        assert doc.metadata["chunk"] == i + 1
        assert doc.metadata["total_chunks"] == len(result)


def test_parse_text_to_docs_empty(text_handler):
    """Test parse_text_to_docs with empty string returns empty list."""
    metadata = get_mock_metadata()
    result = text_handler.parse_text_to_docs(b"", metadata)
    assert result == []


def test_parse_text_to_docs_preserves_metadata(text_handler):
    """Test parse_text_to_docs carries over all metadata to each chunk."""
    text = get_mock_text_content()
    metadata = {
        "file_id": "test-id",
        "session_id": "sess-id",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test.txt",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = text_handler.parse_text_to_docs(text.encode("utf-8"), metadata)

    for doc in result:
        assert doc.metadata["file_id"] == "test-id"
        assert doc.metadata["session_id"] == "sess-id"


# ============================================
#           EMAIL HANDLER TESTS
# ============================================

# --- parse_eml_to_docs ---

def test_parse_eml_to_docs_plain_text(email_handler):
    """Test parse_eml_to_docs extracts text from plain text email."""
    raw = get_mock_eml_plain_text()
    metadata = get_mock_eml_metadata()

    result = email_handler.parse_eml_to_docs(raw, metadata)

    assert len(result) >= 1
    assert isinstance(result[0], Document)
    assert "eiendomssaken" in result[0].page_content
    assert result[0].metadata["file_id"] == metadata["file_id"]
    assert result[0].metadata["session_id"] == metadata["session_id"]
    assert "chunk" in result[0].metadata
    assert "total_chunks" in result[0].metadata


def test_parse_eml_to_docs_multipart(email_handler):
    """Test parse_eml_to_docs extracts text from multipart email."""
    raw = get_mock_eml_multipart()
    metadata = get_mock_eml_metadata()

    result = email_handler.parse_eml_to_docs(raw, metadata)

    assert len(result) >= 1
    assert isinstance(result[0], Document)
    assert "Befaring" in result[0].page_content


def test_parse_eml_to_docs_with_attachment(email_handler):
    """Test parse_eml_to_docs processes email body (not attachments) into documents."""
    raw = get_mock_eml_with_text_attachment()
    metadata = get_mock_eml_metadata()

    result = email_handler.parse_eml_to_docs(raw, metadata)

    assert len(result) >= 1
    assert any("vedlagt" in doc.page_content.lower() for doc in result)


def test_parse_eml_to_docs_preserves_metadata(email_handler):
    """Test parse_eml_to_docs preserves all metadata across chunks."""
    raw = get_mock_eml_plain_text()
    metadata = {
        "file_id": "eml-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test-email.eml",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = email_handler.parse_eml_to_docs(raw, metadata)

    for doc in result:
        assert doc.metadata["file_id"] == "eml-001"
        assert doc.metadata["session_id"] == "s-001"


def test_parse_eml_to_docs_invalid_bytes(email_handler):
    """Test parse_eml_to_docs with invalid bytes."""
    metadata = get_mock_eml_metadata()
    result = email_handler.parse_eml_to_docs(b"not a real email", metadata)
    assert isinstance(result, list)


# ============================================
#           DOCX HANDLER TESTS
# ============================================

# --- parse_docx_to_docs ---

def test_parse_docx_to_docs_with_real_file(docx_handler):
    """Test parse_docx_to_docs extracts text from real Word document."""
    content = get_mock_docx_bytes()
    metadata = get_mock_metadata()

    result = docx_handler.parse_docx_to_docs(content, metadata)

    assert len(result) > 0
    assert isinstance(result[0], Document)
    assert result[0].metadata["file_id"] == metadata["file_id"]
    assert result[0].metadata["session_id"] == metadata["session_id"]
    assert "chunk" in result[0].metadata
    assert "total_chunks" in result[0].metadata
    assert len(result[0].page_content) > 0


def test_parse_docx_to_docs_empty_document(docx_handler):
    """Test parse_docx_to_docs with document containing no text."""
    content = b"fake docx bytes"
    metadata = get_mock_metadata()

    with patch('documents.document_modules.DocxDocument') as mock_docx:
        mock_doc = MagicMock()

        mock_props = MagicMock()
        mock_props.title = None
        mock_props.author = None
        mock_props.created = datetime(2024, 1, 15)
        mock_props.modified = datetime(2024, 1, 15)
        mock_props.comments = None
        mock_props.language = None
        mock_doc.core_properties = mock_props

        para1 = MagicMock()
        para1.text = ""
        para2 = MagicMock()
        para2.text = "   "
        mock_doc.paragraphs = [para1, para2]
        mock_docx.return_value = mock_doc

        result = docx_handler.parse_docx_to_docs(content, metadata)
        assert result == []


def test_parse_docx_to_docs_invalid_bytes(docx_handler):
    """Test parse_docx_to_docs with invalid bytes returns empty list."""
    content = b"not a real docx file"
    metadata = get_mock_metadata()

    with patch('documents.document_modules.DocxDocument', side_effect=Exception("Invalid DOCX")):
        result = docx_handler.parse_docx_to_docs(content, metadata)
        assert result == []


def test_parse_docx_to_docs_preserves_metadata(docx_handler):
    """Test parse_docx_to_docs carries over all metadata to each chunk."""
    content = get_mock_docx_bytes()
    metadata = {
        "file_id": "doc-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test.docx",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = docx_handler.parse_docx_to_docs(content, metadata)

    assert len(result) > 0
    for doc in result:
        assert doc.metadata["file_id"] == "doc-001"
        assert doc.metadata["session_id"] == "s-001"


# ============================================
#           PPTX HANDLER TESTS
# ============================================

# --- parse_pptx_to_docs ---

def test_parse_pptx_to_docs_with_real_file(pptx_handler):
    """Test parse_pptx_to_docs extracts text from real PowerPoint presentation."""
    content = get_mock_pptx_bytes()
    metadata = get_mock_metadata()

    result = pptx_handler.parse_pptx_to_docs(content, metadata)

    assert len(result) > 0
    assert isinstance(result[0], Document)
    assert result[0].metadata["file_id"] == metadata["file_id"]
    assert result[0].metadata["session_id"] == metadata["session_id"]
    assert "chunk" in result[0].metadata
    assert "total_chunks" in result[0].metadata
    assert len(result[0].page_content) > 0


def test_parse_pptx_to_docs_empty_presentation(pptx_handler):
    """Test parse_pptx_to_docs with presentation containing no text."""
    content = b"fake pptx bytes"
    metadata = get_mock_metadata()

    with patch('documents.document_modules.Presentation') as mock_pptx:
        mock_pres = MagicMock()

        mock_props = MagicMock()
        mock_props.title = None
        mock_props.author = None
        mock_props.created = datetime(2024, 1, 15)
        mock_props.modified = datetime(2024, 1, 15)
        mock_props.comments = None
        mock_props.language = None
        mock_pres.core_properties = mock_props

        slide1 = MagicMock()
        shape1 = MagicMock()
        shape1.text = ""
        slide1.shapes = [shape1]
        mock_pres.slides = [slide1]
        mock_pptx.return_value = mock_pres

        result = pptx_handler.parse_pptx_to_docs(content, metadata)
        assert result == []


def test_parse_pptx_to_docs_invalid_bytes(pptx_handler):
    """Test parse_pptx_to_docs with invalid bytes returns empty list."""
    content = b"not a real pptx file"
    metadata = get_mock_metadata()

    with patch('documents.document_modules.Presentation', side_effect=Exception("Invalid PPTX")):
        result = pptx_handler.parse_pptx_to_docs(content, metadata)
        assert result == []


def test_parse_pptx_to_docs_preserves_metadata(pptx_handler):
    """Test parse_pptx_to_docs carries over all metadata to each chunk."""
    content = get_mock_pptx_bytes()
    metadata = {
        "file_id": "ppt-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test.pptx",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = pptx_handler.parse_pptx_to_docs(content, metadata)

    assert len(result) > 0
    for doc in result:
        assert doc.metadata["file_id"] == "ppt-001"
        assert doc.metadata["session_id"] == "s-001"


# ============================================
#    DOCUMENT PROCESSOR ROUTING TESTS
# ============================================

# --- parse (main entry point) ---

def test_parse_routes_pdf(doc_processor):
    """Test parse() routes PDF to PDFHandler.parse_pdf_to_docs."""
    content = get_mock_pdf_base64_with_text()
    metadata = get_mock_metadata()

    with patch.object(PDFHandler, 'parse_pdf_to_docs', return_value=[Document(page_content="parsed")]) as mock_parse:
        result = doc_processor.parse(
            content=content,
            file_type="application/pdf",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        assert isinstance(call_args.args[0], bytes)


def test_parse_routes_text(doc_processor):
    """Test parse() routes text/plain to TextHandler.parse_text_to_docs."""
    text_content = get_mock_text_content()
    b64_content = base64.b64encode(text_content.encode("utf-8")).decode("utf-8")
    metadata = get_mock_metadata()

    with patch.object(TextHandler, 'parse_text_to_docs', return_value=[Document(page_content="parsed")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="text/plain",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


def test_parse_routes_eml(doc_processor):
    """Test parse() routes message/rfc822 to EmailHandler.parse_eml_to_docs."""
    b64_content = get_mock_eml_plain_text_b64()
    metadata = get_mock_eml_metadata()

    with patch.object(EmailHandler, 'parse_eml_to_docs', return_value=[Document(page_content="email text")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="message/rfc822",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        assert len(result) == 1


def test_parse_routes_csv(doc_processor):
    """Test parse() routes text/csv to TextHandler.parse_csv_to_docs."""
    csv_content = "col1,col2\nval1,val2"
    b64_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
    metadata = get_mock_metadata()

    with patch.object(TextHandler, 'parse_csv_to_docs', return_value=[Document(page_content="csv data")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="text/csv",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


def test_parse_routes_docx(doc_processor):
    """Test parse() routes docx to DocxHandler.parse_docx_to_docs."""
    b64_content = get_mock_docx_base64()
    metadata = get_mock_metadata()

    with patch.object(DocxHandler, 'parse_docx_to_docs', return_value=[Document(page_content="docx parsed")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        assert isinstance(call_args.args[0], bytes)


def test_parse_routes_pptx(doc_processor):
    """Test parse() routes pptx to PptxHandler.parse_pptx_to_docs."""
    b64_content = get_mock_pptx_base64()
    metadata = get_mock_metadata()

    with patch.object(PptxHandler, 'parse_pptx_to_docs', return_value=[Document(page_content="pptx parsed")]) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        assert isinstance(call_args.args[0], bytes)


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
    """Test parse() raises ValueError when metadata is missing required fields."""
    with pytest.raises(ValueError, match="Metadata must include"):
        doc_processor.parse(
            content="dGVzdA==",
            file_type="text/plain",
            metadata={"file_id": "test"},
        )

    with pytest.raises(ValueError, match="Metadata must include"):
        doc_processor.parse(
            content="dGVzdA==",
            file_type="text/plain",
            metadata={"file_id": "test", "session_id": "sess"},
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
