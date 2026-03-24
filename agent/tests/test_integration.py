"""
Integration tests for storage, document parsing, and tools.

These tests require real external services and are skipped automatically
when the required environment variables are not set.

Run only integration tests:
    pytest -m integration

Skip integration tests (default CI behaviour):
    pytest -m "not integration"
"""
import os
import sys
import uuid
import base64
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tests.fixtures.vectorstore_data import (
    get_mock_docx_bytes,
    get_mock_pptx_bytes,
    get_mock_metadata,
    get_mock_pdf_bytes_with_text,
    get_mock_text_content,
)
from tests.fixtures.storage_data import get_mock_pdf_attachment, get_mock_text_attachment

# ============================================
#           HELPERS / MARKERS
# ============================================

requires_supabase = pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")),
    reason="SUPABASE_URL and SUPABASE_KEY must be set for storage integration tests",
)

requires_gcp = pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    reason="GOOGLE_APPLICATION_CREDENTIALS must be set for GCP integration tests",
)


# ============================================
#           DOCUMENT MODULE
# ============================================
# These tests parse real fixture files — no external services needed.

@pytest.mark.integration
def test_integration_parse_docx_real_file():
    """Parse real DOCX fixture and verify text is extracted."""
    from documents import DocxHandler

    handler = DocxHandler()
    content = get_mock_docx_bytes()
    metadata = get_mock_metadata()

    text, meta = handler.parse_docx(content, metadata)

    assert isinstance(text, str)
    assert len(text) > 0
    assert meta["file_id"] == metadata["file_id"]
    assert meta["session_id"] == metadata["session_id"]
    assert "wordprocessingml" in meta["file_type"]


@pytest.mark.integration
def test_integration_parse_pptx_real_file():
    """Parse real PPTX fixture and verify text is extracted."""
    from documents import PptxHandler

    handler = PptxHandler()
    content = get_mock_pptx_bytes()
    metadata = get_mock_metadata()

    text, meta = handler.parse_pptx(content, metadata)

    assert isinstance(text, str)
    assert len(text) > 0
    assert meta["file_id"] == metadata["file_id"]
    assert "presentationml" in meta["file_type"]


@pytest.mark.integration
def test_integration_document_processor_routes_pdf():
    """DocumentProcessor routes PDF bytes through the correct handler."""
    from langchain_core.documents import Document
    from documents import DocumentProcessor
    from utils import get_app_config

    config = get_app_config()
    processor = DocumentProcessor(config=config)

    content = get_mock_pdf_bytes_with_text()
    metadata = get_mock_metadata()
    file_type = processor.map_file_type(".pdf")

    docs = processor.parse(
        content=content,
        metadata=metadata,
        file_type=file_type,
        force_metadata_model=False,
    )

    assert isinstance(docs, list)
    assert len(docs) > 0
    assert all(isinstance(d, Document) for d in docs)
    assert any(d.page_content for d in docs)


@pytest.mark.integration
def test_integration_document_processor_routes_docx():
    """DocumentProcessor routes DOCX bytes through the correct handler."""
    from langchain_core.documents import Document
    from documents import DocumentProcessor
    from utils import get_app_config

    config = get_app_config()
    processor = DocumentProcessor(config=config)

    content = get_mock_docx_bytes()
    metadata = get_mock_metadata()
    file_type = processor.map_file_type(".docx")

    docs = processor.parse(
        content=content,
        metadata=metadata,
        file_type=file_type,
        force_metadata_model=False,
    )

    assert isinstance(docs, list)
    assert len(docs) > 0
    assert all(isinstance(d, Document) for d in docs)


@pytest.mark.integration
def test_integration_document_processor_routes_pptx():
    """DocumentProcessor routes PPTX bytes through the correct handler."""
    from langchain_core.documents import Document
    from documents import DocumentProcessor
    from utils import get_app_config

    config = get_app_config()
    processor = DocumentProcessor(config=config)

    content = get_mock_pptx_bytes()
    metadata = get_mock_metadata()
    file_type = processor.map_file_type(".pptx")

    docs = processor.parse(
        content=content,
        metadata=metadata,
        file_type=file_type,
        force_metadata_model=False,
    )

    assert isinstance(docs, list)
    assert len(docs) > 0
    assert all(isinstance(d, Document) for d in docs)


# ============================================
#           STORAGE — SUPABASE
# ============================================

@pytest.mark.integration
@requires_supabase
def test_integration_supabase_save_and_read_attachment():
    """Upload bytes to Supabase Storage and read them back."""
    from database import SupabaseStorageManager
    from utils import get_app_config

    config = get_app_config()
    manager = SupabaseStorageManager(config=config)

    test_id = str(uuid.uuid4())
    path = f"integration-test/{test_id}.txt"
    content = b"Integration test content: " + test_id.encode()

    try:
        saved_path = manager.save_attachment(content=content, path=path)
        assert saved_path == path, f"Expected path {path}, got {saved_path}"

        downloaded = manager.read_attachment(path)
        assert downloaded == content, "Downloaded content does not match uploaded content"
    finally:
        manager.delete_attachment(path)


@pytest.mark.integration
@requires_supabase
def test_integration_supabase_save_attachment_idempotent():
    """Uploading the same file twice treats the duplicate as success."""
    from database import SupabaseStorageManager
    from utils import get_app_config

    config = get_app_config()
    manager = SupabaseStorageManager(config=config)

    test_id = str(uuid.uuid4())
    path = f"integration-test/{test_id}.txt"
    content = b"Idempotent upload test"

    try:
        first = manager.save_attachment(content=content, path=path)
        second = manager.save_attachment(content=content, path=path)
        assert first == path
        assert second == path
    finally:
        manager.delete_attachment(path)


@pytest.mark.integration
@requires_supabase
async def test_integration_supabase_save_raw_documents():
    """save_raw_documents uploads all attachments and returns True."""
    from database import SupabaseStorageManager
    from utils import get_app_config
    from models.api_request_models import AttachmentModel

    config = get_app_config()
    manager = SupabaseStorageManager(config=config)

    uid = str(uuid.uuid4())[:8]
    pdf_att = get_mock_pdf_attachment()
    text_att = get_mock_text_attachment()
    pdf_att.path = f"integration-test/pdf-{uid}.pdf"
    text_att.path = f"integration-test/txt-{uid}.txt"

    try:
        result = await manager.save_raw_documents([pdf_att, text_att])
        assert result is True

        pdf_downloaded = manager.read_attachment(pdf_att.path)
        txt_downloaded = manager.read_attachment(text_att.path)
        assert pdf_downloaded is not None
        assert txt_downloaded is not None
    finally:
        manager.delete_attachment(pdf_att.path)
        manager.delete_attachment(text_att.path)


@pytest.mark.integration
@requires_supabase
def test_integration_supabase_read_attachments_missing_returns_none():
    """read_attachments returns None for paths that do not exist."""
    from database import SupabaseStorageManager
    from utils import get_app_config

    config = get_app_config()
    manager = SupabaseStorageManager(config=config)

    missing_path = f"integration-test/does-not-exist-{uuid.uuid4()}.pdf"
    results = manager.read_attachments([missing_path])

    assert results[missing_path] is None


# ============================================
#           STORAGE — GCS
# ============================================

@pytest.mark.integration
@requires_gcp
def test_integration_gcs_save_and_read_attachment():
    """Upload bytes to GCS and read them back."""
    from database import GCSManager
    from utils import get_app_config

    config = get_app_config()
    manager = GCSManager(config=config)

    test_id = str(uuid.uuid4())
    path = f"integration-test/{test_id}.txt"
    content = b"GCS integration test: " + test_id.encode()

    try:
        saved_path = manager.save_attachment(content=content, path=path)
        assert saved_path == path

        downloaded = manager.read_attachment(path)
        assert downloaded == content
    finally:
        manager.delete_attachment(path)


# ============================================
#           TOOLS
# ============================================

@pytest.mark.integration
@requires_supabase
def test_integration_read_attachments_tool_with_body():
    """read_attachments returns body text when the DB has cached body content."""
    from unittest.mock import MagicMock, patch
    from agent.tools import read_attachments

    mock_sm = MagicMock()
    mock_sm.get_body_by_id.return_value = [
        {"body": "Cached document content from DB", "path": "user/session/file-001.pdf"}
    ]
    mock_storage = MagicMock()

    with patch('agent.tools.SupabaseManager', return_value=mock_sm), \
         patch('agent.tools.SupabaseStorageManager', return_value=mock_storage):
        result = read_attachments.invoke({"ids": ["file-001"]})

    assert "Cached document content from DB" in result
    mock_storage.read_attachments.assert_not_called()


@pytest.mark.integration
@requires_supabase
def test_integration_read_attachments_tool_falls_back_to_storage():
    """read_attachments falls back to storage when body is not cached."""
    from unittest.mock import MagicMock, patch
    from agent.tools import read_attachments
    from documents import DocumentProcessor
    from utils import get_app_config

    config = get_app_config()
    pdf_bytes = get_mock_pdf_bytes_with_text()

    mock_sm = MagicMock()
    mock_sm.get_body_by_id.return_value = [
        {"body": None, "path": "user/session/test-doc.pdf"}
    ]

    mock_storage = MagicMock()
    mock_storage.read_attachments.return_value = {
        "user/session/test-doc.pdf": pdf_bytes
    }

    with patch('agent.tools.SupabaseManager', return_value=mock_sm), \
         patch('agent.tools.SupabaseStorageManager', return_value=mock_storage):
        result = read_attachments.invoke({"ids": ["test-doc"]})

    assert "CONTENT FOR FILE-ID test-doc" in result
    mock_storage.read_attachments.assert_called_once_with(paths=["user/session/test-doc.pdf"])
