import pytest
from unittest.mock import MagicMock, patch
import sys
import os
import base64
import threading
import time

from tests.fixtures.storage_data import *

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SupabaseStorageManager


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.storage.max_retries = 3
    config.storage.max_concurrent_uploads = 5
    config.storage.supabase.bucket_name = "attachments"
    return config


@pytest.fixture
def mock_storage_manager(mock_config):
    """
    Pytest fixture that creates a SupabaseStorageManager with a mocked Supabase client.
    """
    with patch('database.storage_supabase.create_client') as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        manager = SupabaseStorageManager(config=mock_config)
        yield manager


# ============================================
#           save_attachment
# ============================================

def test_save_attachment_with_bytes(mock_storage_manager):
    """Test save_attachment with bytes content."""
    content = b"raw bytes content"
    path = "user123/session456/file.pdf"

    result = mock_storage_manager.save_attachment(content=content, path=path)

    mock_storage_manager.bucket.upload.assert_called_once()
    upload_kwargs = mock_storage_manager.bucket.upload.call_args
    assert upload_kwargs.kwargs["path"] == path
    assert result == path


def test_save_attachment_only_accepts_bytes(mock_storage_manager):
    """Test save_attachment returns None when given non-bytes content."""
    content = "string content"  # Not bytes
    path = "user123/session456/file.txt"

    result = mock_storage_manager.save_attachment(content=content, path=path)

    assert result is None


def test_save_attachment_handles_error(mock_storage_manager):
    """Test save_attachment handles upload errors gracefully and returns None."""
    mock_storage_manager.bucket.upload.side_effect = Exception("Upload failed")
    content = b"some content"
    path = "user123/session456/file.pdf"

    result = mock_storage_manager.save_attachment(content=content, path=path)
    assert result is None


def test_save_attachment_treats_duplicate_as_success(mock_storage_manager):
    """Test save_attachment treats 409/Duplicate errors as success."""
    mock_storage_manager.bucket.upload.side_effect = Exception("409 Duplicate")
    content = b"some content"
    path = "user123/session456/file.pdf"

    result = mock_storage_manager.save_attachment(content=content, path=path)
    assert result == path


# ============================================
#           save_raw_documents
# ============================================

@pytest.mark.asyncio
async def test_save_raw_documents_pdf_and_text(mock_storage_manager):
    """Test save_raw_documents processes both PDF and text attachments (both base64-encoded)."""
    attachments = get_mock_attachments_list()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = "path/to/file"
        results = await mock_storage_manager.save_raw_documents(attachments)
        assert mock_save.call_count == 2
        assert results is True

        for call in mock_save.call_args_list:
            content_arg = call.kwargs.get("content") or call[0][0]
            assert isinstance(content_arg, bytes), "All content must be bytes"


@pytest.mark.asyncio
async def test_save_raw_documents_decodes_base64(mock_storage_manager):
    """Test that all content is base64-decoded before saving."""
    pdf_att = get_mock_pdf_attachment()
    text_att = get_mock_text_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = pdf_att.path
        results = await mock_storage_manager.save_raw_documents([pdf_att, text_att])

        assert mock_save.call_count == 2

        for call in mock_save.call_args_list:
            content_arg = call.kwargs.get("content") or call[0][0]
            assert isinstance(content_arg, bytes), "All content must be decoded to bytes"
            assert content_arg != pdf_att.content
            assert content_arg != text_att.content


@pytest.mark.asyncio
async def test_save_raw_documents_uses_correct_paths(mock_storage_manager):
    """Test that each attachment uses its own path."""
    attachments = get_mock_attachments_list()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = "path/to/file"
        results = await mock_storage_manager.save_raw_documents(attachments)

        paths_used = [c.kwargs.get("path") or c[1].get("path") for c in mock_save.call_args_list]
        assert attachments[0].path in paths_used
        assert attachments[1].path in paths_used
        assert results is True


@pytest.mark.asyncio
async def test_save_raw_documents_empty_list(mock_storage_manager):
    """Test save_raw_documents handles empty attachment list."""
    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        results = await mock_storage_manager.save_raw_documents([])
        mock_save.assert_not_called()
        assert results is True


# ============================================
#      Retry Logic & Semaphore Tests
# ============================================

def test_save_attachment_retries_on_resource_unavailable(mock_storage_manager):
    """Test save_attachment retries on 'Resource temporarily unavailable' error."""
    content = b"some content"
    path = "user123/session456/file.pdf"

    mock_storage_manager.bucket.upload.side_effect = [
        Exception("[Errno 35] Resource temporarily unavailable"),
        Exception("[Errno 35] Resource temporarily unavailable"),
        None  # Success
    ]

    with patch('time.sleep'):
        result = mock_storage_manager.save_attachment(content=content, path=path)

    assert mock_storage_manager.bucket.upload.call_count == 3
    assert result == path


def test_save_attachment_gives_up_after_max_retries(mock_storage_manager):
    """Test save_attachment gives up after config.storage.max_retries attempts."""
    content = b"some content"
    path = "user123/session456/file.pdf"

    mock_storage_manager.bucket.upload.side_effect = Exception(
        "[Errno 35] Resource temporarily unavailable"
    )

    with patch('time.sleep'):
        result = mock_storage_manager.save_attachment(content=content, path=path)

    assert mock_storage_manager.bucket.upload.call_count == 3  # max_retries=3
    assert result is None


def test_save_attachment_no_retry_on_other_errors(mock_storage_manager):
    """Test save_attachment doesn't retry on non-transient errors."""
    content = b"some content"
    path = "user123/session456/file.pdf"

    mock_storage_manager.bucket.upload.side_effect = Exception("Invalid credentials")

    result = mock_storage_manager.save_attachment(content=content, path=path)

    assert mock_storage_manager.bucket.upload.call_count == 1
    assert result is None


@pytest.mark.asyncio
async def test_save_raw_documents_respects_semaphore():
    """Test save_raw_documents uses semaphore to limit concurrent uploads."""
    config = MagicMock()
    config.storage.max_concurrent_uploads = 2
    config.storage.supabase.bucket_name = "attachments"
    config.storage.max_retries = 3

    with patch('database.storage_supabase.create_client'):
        manager = SupabaseStorageManager(config=config)

    concurrent_calls = 0
    max_concurrent_calls = 0
    lock = threading.Lock()

    def mock_upload_sync(*args, **kwargs):
        nonlocal concurrent_calls, max_concurrent_calls
        with lock:
            concurrent_calls += 1
            max_concurrent_calls = max(max_concurrent_calls, concurrent_calls)
        time.sleep(0.01)
        with lock:
            concurrent_calls -= 1
        return kwargs.get('path', 'default/path')

    attachments = [get_mock_text_attachment() for _ in range(5)]
    for i, att in enumerate(attachments):
        att.file_id = f"file_{i}"
        att.path = f"path/to/file_{i}.txt"

    with patch.object(manager, 'save_attachment', side_effect=mock_upload_sync):
        results = await manager.save_raw_documents(attachments)

    assert results is True
    assert max_concurrent_calls <= 2


@pytest.mark.asyncio
async def test_save_raw_documents_handles_mixed_success_failure(mock_storage_manager):
    """Test save_raw_documents handles mix of successful and failed uploads."""
    attachments = get_mock_attachments_list()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.side_effect = [attachments[0].path, None]
        results = await mock_storage_manager.save_raw_documents(attachments)

    assert results is True


# ============================================
#           read_attachment
# ============================================

def test_read_attachment(mock_storage_manager):
    """Test read_attachment downloads from Supabase Storage."""
    path = "user123/session456/file.pdf"
    expected_content = b"downloaded content"

    mock_storage_manager.bucket.download.return_value = expected_content

    result = mock_storage_manager.read_attachment(path)

    mock_storage_manager.bucket.download.assert_called_once_with(path)
    assert result == expected_content


def test_read_attachment_returns_none_on_error(mock_storage_manager):
    """Test read_attachments returns None for failed downloads."""
    path = "user123/session456/missing.pdf"

    mock_storage_manager.bucket.download.side_effect = Exception("Not found")

    results = mock_storage_manager.read_attachments([path])

    assert results[path] is None
