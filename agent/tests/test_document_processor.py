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
    get_mock_eml_plain_text_b64,
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
