import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import os
from datetime import datetime

from tests.fixtures.vectorstore_data import *


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


# ============================================
#           DOCUMENT PROCESSOR TESTS
# ============================================

from documents import PptxHandler, DocxHandler


@pytest.fixture
def docx_handler():
    """DocxHandler instance."""
    return DocxHandler()


@pytest.fixture
def pptx_handler():
    """PptxHandler instance."""
    return PptxHandler()



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
