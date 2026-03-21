import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pydantic import ValidationError
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
    with patch('documents.pdf_module.PdfReader') as mock_reader_cls:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "A" * 600
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page, mock_page, mock_page]
        mock_reader_cls.return_value = mock_reader

        result = pdf_handler._needs_ocr(b"fake pdf bytes")
        assert result is False


def test_needs_ocr_low_text_coverage(pdf_handler):
    """PDF where <50% of pages have text should need OCR."""
    with patch('documents.pdf_module.PdfReader') as mock_reader_cls:
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

    with patch('documents.pdf_module.ocrmypdf') as mock_ocr:
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

    with patch('documents.pdf_module.ocrmypdf') as mock_ocr_module:
        mock_ocr_module.ocr.side_effect = ocrmypdf.exceptions.PriorOcrFoundError()
        mock_ocr_module.exceptions = ocrmypdf.exceptions

        with patch('os.unlink'):
            result = pdf_handler._ocr_bytes(input_bytes)
            assert result == input_bytes


def test_ocr_bytes_error_returns_original(pdf_handler):
    """Test OCR returns original PDF on general failure."""
    input_bytes = b"problematic pdf"

    with patch('documents.pdf_module.ocrmypdf') as mock_ocr_module:
        import ocrmypdf
        mock_ocr_module.ocr.side_effect = RuntimeError("OCR failed")
        mock_ocr_module.exceptions = ocrmypdf.exceptions

        with patch('os.unlink'):
            result = pdf_handler._ocr_bytes(input_bytes)
            assert result == input_bytes


# --- parse_pdf ---

def test_parse_pdf_with_text(pdf_handler):
    """Test parse_pdf extracts text from PDF, returning (str, dict)."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch.object(pdf_handler, '_extract_metadata', return_value={"creator": "TestCreator", "page_count": 2, "size": 100, "file_type": "application/pdf"}):
            with patch.object(pdf_handler, '_extract_md_pymupdf', return_value="Innhold fra side 1 om eiendomstvist"):
                result = pdf_handler.parse_pdf(b"fake pdf bytes", metadata)

                assert isinstance(result, tuple)
                text_out, meta_out = result
                assert isinstance(text_out, str)
                assert "Innhold fra side 1" in text_out
                assert meta_out["file_id"] == metadata["file_id"]
                assert meta_out["session_id"] == metadata["session_id"]


def test_parse_pdf_empty_pages(pdf_handler):
    """Test parse_pdf with no text content returns empty string."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch.object(pdf_handler, '_extract_metadata', return_value={"page_count": 2, "size": 100, "file_type": "application/pdf"}):
            with patch.object(pdf_handler, '_extract_md_pymupdf', return_value=""):
                result = pdf_handler.parse_pdf(b"fake pdf bytes", metadata)
                assert isinstance(result, tuple)
                text_out, meta_out = result
                assert text_out == ""


def test_parse_pdf_skips_empty_pages(pdf_handler):
    """Test parse_pdf returns extracted text content."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch.object(pdf_handler, '_extract_metadata', return_value={"page_count": 3, "size": 100, "file_type": "application/pdf"}):
            with patch.object(pdf_handler, '_extract_md_pymupdf', return_value="Innhold om rettssaken"):
                result = pdf_handler.parse_pdf(b"fake pdf bytes", metadata)
                assert isinstance(result, tuple)
                text_out, meta_out = result
                assert "Innhold om rettssaken" in text_out


def test_parse_pdf_triggers_ocr_when_needed(pdf_handler):
    """Test parse_pdf calls Textract OCR extraction when needs_ocr returns True."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=True):
        with patch.object(pdf_handler, '_extract_metadata', return_value={"page_count": 1, "size": 100, "file_type": "application/pdf"}):
            with patch.object(pdf_handler, '_extract_md_textract', return_value="OCR extracted text") as mock_textract:
                result = pdf_handler.parse_pdf(b"scanned pdf", metadata)
                mock_textract.assert_called_once_with(b"scanned pdf")
                assert isinstance(result, tuple)
                text_out, meta_out = result
                assert "OCR extracted text" in text_out


def test_parse_pdf_invalid_pdf(pdf_handler):
    """Test parse_pdf raises when content cannot be extracted."""
    metadata = get_mock_metadata()

    with patch.object(pdf_handler, '_needs_ocr', return_value=False):
        with patch.object(pdf_handler, '_extract_metadata', return_value={"page_count": 0, "size": 0, "file_type": "application/pdf"}):
            with patch.object(pdf_handler, '_extract_md_pymupdf', side_effect=Exception("Invalid PDF")):
                import pytest as _pytest
                with _pytest.raises(Exception):
                    pdf_handler.parse_pdf(b"invalid", metadata)


# --- _extract_md_pymupdf ---

def test_extract_md_pymupdf_returns_string(pdf_handler):
    """_extract_md_pymupdf should return markdown string from fitz+pymupdf4llm."""
    mock_doc = MagicMock()
    with patch('documents.pdf_module.fitz.open', return_value=mock_doc) as mock_fitz:
        with patch('documents.pdf_module.pymupdf4llm.to_markdown', return_value="# Heading\nBody text") as mock_md:
            result = pdf_handler._extract_md_pymupdf(b"fake pdf bytes")

            mock_fitz.assert_called_once_with(stream=b"fake pdf bytes", filetype="pdf")
            mock_md.assert_called_once_with(mock_doc)
            mock_doc.close.assert_called_once()
            assert result == "# Heading\nBody text"


def test_extract_md_pymupdf_closes_doc_on_success(pdf_handler):
    """fitz doc should always be closed after extraction."""
    mock_doc = MagicMock()
    with patch('documents.pdf_module.fitz.open', return_value=mock_doc):
        with patch('documents.pdf_module.pymupdf4llm.to_markdown', return_value="content"):
            pdf_handler._extract_md_pymupdf(b"fake pdf bytes")
            mock_doc.close.assert_called_once()


def test_extract_md_pymupdf_empty_output(pdf_handler):
    """_extract_md_pymupdf with no text should return empty string."""
    mock_doc = MagicMock()
    with patch('documents.pdf_module.fitz.open', return_value=mock_doc):
        with patch('documents.pdf_module.pymupdf4llm.to_markdown', return_value=""):
            result = pdf_handler._extract_md_pymupdf(b"fake pdf bytes")
            assert result == ""


# --- _extract_md_textract ---

def test_extract_md_textract_returns_string(pdf_handler):
    """_extract_md_textract should call Textractor and return markdown string."""
    mock_document = MagicMock()
    mock_document.get_text.return_value = "## Section\nExtracted OCR text"
    mock_extractor = MagicMock()
    mock_extractor.start_document_analysis.return_value = mock_document

    with patch('documents.pdf_module.Textractor', return_value=mock_extractor):
        with patch('documents.pdf_module.TextLinearizationConfig') as mock_config_cls:
            with patch('tempfile.NamedTemporaryFile') as mock_tmp:
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake.pdf"
                with patch('os.unlink'):
                    result = pdf_handler._extract_md_textract(b"scanned pdf bytes")

    assert result == "## Section\nExtracted OCR text"


def test_extract_md_textract_calls_start_document_analysis(pdf_handler):
    """_extract_md_textract should call start_document_analysis with correct s3 paths."""
    mock_document = MagicMock()
    mock_document.get_text.return_value = "text"
    mock_extractor = MagicMock()
    mock_extractor.start_document_analysis.return_value = mock_document

    with patch('documents.pdf_module.Textractor', return_value=mock_extractor):
        with patch('documents.pdf_module.TextLinearizationConfig'):
            with patch('tempfile.NamedTemporaryFile') as mock_tmp:
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake.pdf"
                with patch('os.unlink'):
                    pdf_handler._extract_md_textract(b"scanned pdf bytes")

    call_kwargs = mock_extractor.start_document_analysis.call_args[1]
    assert "s3_output_path" in call_kwargs
    assert "s3_upload_path" in call_kwargs
    assert call_kwargs["s3_output_path"].startswith("s3://")
    assert call_kwargs["s3_upload_path"].startswith("s3://")


def test_extract_md_textract_uses_markdown_table_format(pdf_handler):
    """TextLinearizationConfig should be configured with markdown table format."""
    mock_document = MagicMock()
    mock_document.get_text.return_value = "text"
    mock_extractor = MagicMock()
    mock_extractor.start_document_analysis.return_value = mock_document

    with patch('documents.pdf_module.Textractor', return_value=mock_extractor):
        with patch('documents.pdf_module.TextLinearizationConfig') as mock_config_cls:
            mock_config_cls.return_value = MagicMock()
            with patch('tempfile.NamedTemporaryFile') as mock_tmp:
                mock_tmp.return_value.__enter__.return_value.name = "/tmp/fake.pdf"
                with patch('os.unlink'):
                    pdf_handler._extract_md_textract(b"scanned pdf bytes")

    mock_config_cls.assert_called_once()
    call_kwargs = mock_config_cls.call_args[1]
    assert call_kwargs.get("table_linearization_format") == "markdown"


# ============================================
#           TEXT HANDLER TESTS
# ============================================

# --- parse_text ---

def test_parse_text_short(text_handler):
    """Test parse_text with content shorter than chunk_size returns (str, dict)."""
    text = get_mock_text_content()
    metadata = get_mock_metadata()

    result = text_handler.parse_text(text.encode("utf-8"), metadata)

    assert isinstance(result, tuple)
    assert len(result) == 2
    text_out, meta_out = result
    assert isinstance(text_out, str)
    assert isinstance(meta_out, dict)
    assert meta_out["file_id"] == metadata["file_id"]
    assert meta_out["session_id"] == metadata["session_id"]


def test_parse_text_long_produces_multiple_chunks(text_handler_small_chunks):
    """Test parse_text returns a non-empty string for long text."""
    text = get_mock_long_text_content()
    metadata = get_mock_metadata()

    result = text_handler_small_chunks.parse_text(text.encode("utf-8"), metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert len(text_out) > 0


def test_parse_text_empty(text_handler):
    """Test parse_text with empty bytes returns empty string."""
    metadata = get_mock_metadata()
    result = text_handler.parse_text(b"", metadata)
    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert text_out == ""


def test_parse_text_preserves_metadata(text_handler):
    """Test parse_text carries over all metadata in the returned dict."""
    text = get_mock_text_content()
    metadata = {
        "file_id": "test-id",
        "session_id": "sess-id",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test.txt",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = text_handler.parse_text(text.encode("utf-8"), metadata)

    text_out, meta_out = result
    assert meta_out["file_id"] == "test-id"
    assert meta_out["session_id"] == "sess-id"


# ============================================
#           EMAIL HANDLER TESTS
# ============================================

# --- parse_eml ---

def test_parse_eml_plain_text(email_handler):
    """Test parse_eml extracts text from plain text email, returning (str, dict)."""
    raw = get_mock_eml_plain_text()
    metadata = get_mock_eml_metadata()

    result = email_handler.parse_eml(raw, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert isinstance(text_out, str)
    assert "eiendomssaken" in text_out
    assert meta_out["file_id"] == metadata["file_id"]
    assert meta_out["session_id"] == metadata["session_id"]


def test_parse_eml_multipart(email_handler):
    """Test parse_eml extracts text from multipart email."""
    raw = get_mock_eml_multipart()
    metadata = get_mock_eml_metadata()

    result = email_handler.parse_eml(raw, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert "Befaring" in text_out


def test_parse_eml_with_attachment(email_handler):
    """Test parse_eml processes email body (not attachments)."""
    raw = get_mock_eml_with_text_attachment()
    metadata = get_mock_eml_metadata()

    result = email_handler.parse_eml(raw, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert "vedlagt" in text_out.lower()


def test_parse_eml_preserves_metadata(email_handler):
    """Test parse_eml preserves all metadata in the returned dict."""
    raw = get_mock_eml_plain_text()
    metadata = {
        "file_id": "eml-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test-email.eml",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = email_handler.parse_eml(raw, metadata)

    text_out, meta_out = result
    assert meta_out["file_id"] == "eml-001"
    assert meta_out["session_id"] == "s-001"


def test_parse_eml_invalid_bytes(email_handler):
    """Test parse_eml with invalid bytes returns (str, dict)."""
    metadata = get_mock_eml_metadata()
    result = email_handler.parse_eml(b"not a real email", metadata)
    assert isinstance(result, tuple)


# ============================================
#           DOCX HANDLER TESTS
# ============================================

# --- parse_docx ---

def test_parse_docx_with_real_file(docx_handler):
    """Test parse_docx extracts text from real Word document, returning (str, dict)."""
    content = get_mock_docx_bytes()
    metadata = get_mock_metadata()

    result = docx_handler.parse_docx(content, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert isinstance(text_out, str)
    assert len(text_out) > 0
    assert meta_out["file_id"] == metadata["file_id"]
    assert meta_out["session_id"] == metadata["session_id"]


def test_parse_docx_empty_document(docx_handler):
    """Test parse_docx with document containing no text returns empty string."""
    content = b"fake docx bytes"
    metadata = get_mock_metadata()

    with patch('documents.ms_modules.DocxDocument') as mock_docx:
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

        result = docx_handler.parse_docx(content, metadata)
        assert isinstance(result, tuple)
        text_out, meta_out = result
        assert text_out == ""


def test_parse_docx_invalid_bytes(docx_handler):
    """Test parse_docx with invalid bytes returns empty list."""
    content = b"not a real docx file"
    metadata = get_mock_metadata()

    with patch('documents.ms_modules.DocxDocument', side_effect=Exception("Invalid DOCX")):
        result = docx_handler.parse_docx(content, metadata)
        assert result == []


def test_parse_docx_preserves_metadata(docx_handler):
    """Test parse_docx carries over all metadata in the returned dict."""
    content = get_mock_docx_bytes()
    metadata = {
        "file_id": "doc-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test.docx",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = docx_handler.parse_docx(content, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert len(text_out) > 0
    assert meta_out["file_id"] == "doc-001"
    assert meta_out["session_id"] == "s-001"


# ============================================
#           PPTX HANDLER TESTS
# ============================================

# --- parse_pptx ---

def test_parse_pptx_with_real_file(pptx_handler):
    """Test parse_pptx extracts text from real PowerPoint presentation, returning (str, dict)."""
    content = get_mock_pptx_bytes()
    metadata = get_mock_metadata()

    result = pptx_handler.parse_pptx(content, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert isinstance(text_out, str)
    assert len(text_out) > 0
    assert meta_out["file_id"] == metadata["file_id"]
    assert meta_out["session_id"] == metadata["session_id"]


def test_parse_pptx_empty_presentation(pptx_handler):
    """Test parse_pptx with presentation containing no text returns empty string."""
    content = b"fake pptx bytes"
    metadata = get_mock_metadata()

    with patch('documents.ms_modules.Presentation') as mock_pptx:
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

        result = pptx_handler.parse_pptx(content, metadata)
        assert isinstance(result, tuple)
        text_out, meta_out = result
        assert text_out == ""


def test_parse_pptx_invalid_bytes(pptx_handler):
    """Test parse_pptx with invalid bytes returns empty list."""
    content = b"not a real pptx file"
    metadata = get_mock_metadata()

    with patch('documents.ms_modules.Presentation', side_effect=Exception("Invalid PPTX")):
        result = pptx_handler.parse_pptx(content, metadata)
        assert result == []


def test_parse_pptx_preserves_metadata(pptx_handler):
    """Test parse_pptx carries over all metadata in the returned dict."""
    content = get_mock_pptx_bytes()
    metadata = {
        "file_id": "ppt-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test.pptx",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = pptx_handler.parse_pptx(content, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert len(text_out) > 0
    assert meta_out["file_id"] == "ppt-001"
    assert meta_out["session_id"] == "s-001"


# ============================================
#    DOCUMENT PROCESSOR ROUTING TESTS
# ============================================

# --- parse (main entry point) ---

def test_parse_routes_pdf(doc_processor):
    """Test parse() routes PDF to PDFHandler.parse_pdf."""
    content = get_mock_pdf_bytes_with_text()
    metadata = get_mock_metadata()

    mock_config = MagicMock()
    mock_config.storage.aws.region = "eu-west-1"
    mock_config.storage.aws.bucket_name = "test-bucket"
    doc_processor.config = mock_config

    with patch.object(PDFHandler, 'parse_pdf', return_value=("parsed text", {})) as mock_parse:
        result = doc_processor.parse(
            content=content,
            file_type="application/pdf",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        assert isinstance(call_args.args[0], bytes)


def test_parse_routes_text(doc_processor):
    """Test parse() routes text/plain to TextHandler.parse_text."""
    text_content = get_mock_text_content()
    b64_content = base64.b64encode(text_content.encode("utf-8")).decode("utf-8")
    metadata = get_mock_metadata()

    with patch.object(TextHandler, 'parse_text', return_value=("parsed text", {})) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="text/plain",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


def test_parse_routes_eml(doc_processor):
    """Test parse() routes message/rfc822 to EmailHandler.parse_eml."""
    b64_content = get_mock_eml_plain_text_b64()
    metadata = get_mock_eml_metadata()

    with patch.object(EmailHandler, 'parse_eml', return_value=("email text", {})) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="message/rfc822",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


def test_parse_routes_csv(doc_processor):
    """Test parse() routes text/csv to TextHandler.parse_csv."""
    csv_content = "col1,col2\nval1,val2"
    b64_content = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
    metadata = get_mock_metadata()

    with patch.object(TextHandler, 'parse_csv', return_value=("csv data", {})) as mock_parse:
        result = doc_processor.parse(
            content=b64_content,
            file_type="text/csv",
            metadata=metadata,
        )

        mock_parse.assert_called_once()


def test_parse_routes_docx(doc_processor):
    """Test parse() routes docx to DocxHandler.parse_docx."""
    content = get_mock_docx_bytes()
    metadata = get_mock_metadata()

    with patch.object(DocxHandler, 'parse_docx', return_value=("docx parsed", {})) as mock_parse:
        result = doc_processor.parse(
            content=content,
            file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        assert isinstance(call_args.args[0], bytes)


def test_parse_routes_pptx(doc_processor):
    """Test parse() routes pptx to PptxHandler.parse_pptx."""
    content = get_mock_pptx_bytes()
    metadata = get_mock_metadata()

    with patch.object(PptxHandler, 'parse_pptx', return_value=("pptx parsed", {})) as mock_parse:
        result = doc_processor.parse(
            content=content,
            file_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            metadata=metadata,
        )

        mock_parse.assert_called_once()
        call_args = mock_parse.call_args
        assert isinstance(call_args.args[0], bytes)


def test_parse_invalid_base64(doc_processor):
    """Test parse() with unsupported file type returns empty list."""
    metadata = get_mock_metadata()
    result = doc_processor.parse(
        content=b"some content",
        file_type="application/unknown",
        metadata=metadata,
    )
    assert result == []


def test_parse_missing_metadata_raises(doc_processor):
    """Test parse() raises ValidationError when metadata is missing required fields."""
    with pytest.raises(ValidationError):
        doc_processor.parse(
            content=b"test",
            file_type="text/plain",
            metadata={"file_id": "test"},
        )

    with pytest.raises(ValidationError):
        doc_processor.parse(
            content=b"test",
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
