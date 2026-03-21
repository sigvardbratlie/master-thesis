import pytest
from unittest.mock import patch, MagicMock
import sys
import os
from tests.fixtures.vectorstore_data import *


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================
#           DOCUMENT PROCESSOR TESTS
# ============================================

from documents import PDFHandler

@pytest.fixture
def pdf_handler():
    """PDFHandler instance."""
    return PDFHandler()



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

