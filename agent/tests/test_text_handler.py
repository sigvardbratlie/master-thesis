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

from documents import TextHandler


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
