import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import base64

from tests.fixtures.storage_data import *

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SupabaseStorageManager


@pytest.fixture
def mock_storage_manager():
    """
    Pytest fixture som oppretter en SupabaseStorageManager med en mocket Supabase-klient.
    """
    with patch('database.storage_modules.create_client') as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        manager = SupabaseStorageManager(max_concurrent_uploads=5)
        manager.supabase = mock_client
        yield manager
        manager.supabase.reset_mock()


# ============================================
#           save_attachment
# ============================================

def test_save_attachment_with_bytes(mock_storage_manager):
    """Test save_attachment with bytes content."""
    content = b"raw bytes content"
    path = "user123/session456/file.pdf"

    result = mock_storage_manager.save_attachment(content=content, path=path)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with("attachments")
    mock_storage_manager.supabase.storage.from_.return_value.upload.assert_called_once()

    upload_kwargs = mock_storage_manager.supabase.storage.from_.return_value.upload.call_args
    assert upload_kwargs.kwargs["path"] == path
    assert result == path  # Should return path on success


def test_save_attachment_with_string(mock_storage_manager):
    """Test save_attachment converts string to bytes before saving."""
    content = "dette er tekstinnhold"
    path = "user123/session456/file.txt"

    result = mock_storage_manager.save_attachment(content=content, path=path)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with("attachments")
    mock_storage_manager.supabase.storage.from_.return_value.upload.assert_called_once()
    assert result == path  # Should return path on success


def test_save_attachment_custom_bucket(mock_storage_manager):
    """Test save_attachment with custom bucket name."""
    content = b"some content"
    path = "user123/session456/file.pdf"
    bucket = "custom-bucket"

    result = mock_storage_manager.save_attachment(content=content, path=path, bucket_name=bucket)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with(bucket)
    assert result == path


def test_save_attachment_handles_error(mock_storage_manager):
    """Test save_attachment handles upload errors gracefully and returns None."""
    mock_storage_manager.supabase.storage.from_.return_value.upload.side_effect = Exception("Upload failed")
    content = b"some content"
    path = "user123/session456/file.pdf"

    # Should not raise, but return None
    result = mock_storage_manager.save_attachment(content=content, path=path)
    assert result is None


# ============================================
#           save_raw_documents
# ============================================

@pytest.mark.asyncio
async def test_save_raw_documents_pdf_and_text(mock_storage_manager):
    """Test save_raw_documents processes both PDF and text attachments."""
    attachments = get_mock_attachments_list()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = "path/to/file"  # Mock successful upload
        results = await mock_storage_manager.save_raw_documents(attachments)
        assert mock_save.call_count == 2
        assert isinstance(results, dict)
        assert len(results) == 2


@pytest.mark.asyncio
async def test_save_raw_documents_decodes_pdf_base64(mock_storage_manager):
    """Test that PDF content is base64-decoded before saving."""
    pdf_att = get_mock_pdf_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = pdf_att.path
        results = await mock_storage_manager.save_raw_documents([pdf_att])

        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        content_arg = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content") or call_kwargs[0][0]
        # Content should be decoded bytes, not the original base64 string
        assert isinstance(content_arg, bytes)
        assert results[pdf_att.file_id] == pdf_att.path


@pytest.mark.asyncio
async def test_save_raw_documents_text_not_decoded(mock_storage_manager):
    """Test that text content is passed through without base64 decoding."""
    text_att = get_mock_text_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = text_att.path
        results = await mock_storage_manager.save_raw_documents([text_att])

        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        content_arg = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content") or call_kwargs[0][0]
        assert isinstance(content_arg, str)
        assert results[text_att.file_id] == text_att.path


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
        assert len(results) == 2


@pytest.mark.asyncio
async def test_save_raw_documents_custom_bucket(mock_storage_manager):
    """Test save_raw_documents passes custom bucket name."""
    text_att = get_mock_text_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.return_value = text_att.path
        results = await mock_storage_manager.save_raw_documents([text_att], bucket_name="custom-bucket")

        call_kwargs = mock_save.call_args
        bucket_arg = call_kwargs.kwargs.get("bucket_name") or call_kwargs[1].get("bucket_name")
        assert bucket_arg == "custom-bucket"
        assert results[text_att.file_id] == text_att.path


@pytest.mark.asyncio
async def test_save_raw_documents_empty_list(mock_storage_manager):
    """Test save_raw_documents handles empty attachment list."""
    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        results = await mock_storage_manager.save_raw_documents([])
        mock_save.assert_not_called()
        assert results == {}  # Should return empty dict


# ============================================
#      Retry Logic & Semaphore Tests
# ============================================

def test_save_attachment_retries_on_resource_unavailable(mock_storage_manager):
    """Test save_attachment retries on 'Resource temporarily unavailable' error."""
    content = b"some content"
    path = "user123/session456/file.pdf"
    
    # First two calls fail with the specific error, third succeeds
    mock_storage_manager.supabase.storage.from_.return_value.upload.side_effect = [
        Exception("[Errno 35] Resource temporarily unavailable"),
        Exception("[Errno 35] Resource temporarily unavailable"),
        None  # Success
    ]
    
    with patch('time.sleep'):  # Mock sleep to speed up test
        result = mock_storage_manager.save_attachment(content=content, path=path, max_retries=3)
    
    # Should have tried 3 times
    assert mock_storage_manager.supabase.storage.from_.return_value.upload.call_count == 3
    assert result == path  # Should succeed on third try


def test_save_attachment_gives_up_after_max_retries(mock_storage_manager):
    """Test save_attachment gives up after max retries."""
    content = b"some content"
    path = "user123/session456/file.pdf"
    
    # Always fail with the specific error
    mock_storage_manager.supabase.storage.from_.return_value.upload.side_effect = Exception(
        "[Errno 35] Resource temporarily unavailable"
    )
    
    with patch('time.sleep'):  # Mock sleep to speed up test
        result = mock_storage_manager.save_attachment(content=content, path=path, max_retries=3)
    
    # Should have tried 3 times
    assert mock_storage_manager.supabase.storage.from_.return_value.upload.call_count == 3
    assert result is None  # Should return None after all retries failed


def test_save_attachment_no_retry_on_other_errors(mock_storage_manager):
    """Test save_attachment doesn't retry on non-transient errors."""
    content = b"some content"
    path = "user123/session456/file.pdf"
    
    # Fail with a different error (not transient)
    mock_storage_manager.supabase.storage.from_.return_value.upload.side_effect = Exception(
        "Invalid credentials"
    )
    
    result = mock_storage_manager.save_attachment(content=content, path=path, max_retries=3)
    
    # Should only try once (no retry on non-transient errors)
    assert mock_storage_manager.supabase.storage.from_.return_value.upload.call_count == 1
    assert result is None


@pytest.mark.asyncio
async def test_save_raw_documents_respects_semaphore():
    """Test save_raw_documents uses semaphore to limit concurrent uploads."""
    from unittest.mock import AsyncMock
    import asyncio
    
    # Create manager with max 2 concurrent uploads
    with patch('database.storage_modules.create_client'):
        manager = SupabaseStorageManager(max_concurrent_uploads=2)
    
    # Track concurrent calls
    concurrent_calls = 0
    max_concurrent_calls = 0
    
    async def mock_upload(*args, **kwargs):
        nonlocal concurrent_calls, max_concurrent_calls
        concurrent_calls += 1
        max_concurrent_calls = max(max_concurrent_calls, concurrent_calls)
        await asyncio.sleep(0.01)  # Simulate upload time
        concurrent_calls -= 1
        return kwargs.get('path', 'default/path')
    
    # Create 5 attachments
    attachments = [get_mock_text_attachment() for _ in range(5)]
    for i, att in enumerate(attachments):
        att.file_id = f"file_{i}"
        att.path = f"path/to/file_{i}.txt"
    
    with patch.object(manager, 'save_attachment', side_effect=mock_upload):
        results = await manager.save_raw_documents(attachments)
    
    # Should have uploaded all 5 files
    assert len(results) == 5
    # But never more than 2 at the same time
    assert max_concurrent_calls <= 2


@pytest.mark.asyncio
async def test_save_raw_documents_handles_mixed_success_failure(mock_storage_manager):
    """Test save_raw_documents handles mix of successful and failed uploads."""
    attachments = get_mock_attachments_list()
    
    # First upload succeeds, second fails
    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        mock_save.side_effect = [attachments[0].path, None]
        results = await mock_storage_manager.save_raw_documents(attachments)
    
    assert len(results) == 2
    assert results[attachments[0].file_id] == attachments[0].path
    assert results[attachments[1].file_id] is None


# ============================================
#           read_attachment
# ============================================

def test_read_attachment(mock_storage_manager):
    """Test read_attachment downloads from Supabase Storage."""
    path = "user123/session456/file.pdf"
    expected_content = b"downloaded content"

    mock_storage_manager.supabase.storage.from_.return_value.download.return_value = expected_content

    result = mock_storage_manager.read_attachment(path)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with("attachments")
    mock_storage_manager.supabase.storage.from_.return_value.download.assert_called_once_with(path)
    assert result == expected_content


def test_read_attachment_custom_bucket(mock_storage_manager):
    """Test read_attachment with custom bucket name."""
    path = "user123/session456/file.pdf"
    bucket = "custom-bucket"

    mock_storage_manager.supabase.storage.from_.return_value.download.return_value = b"content"

    mock_storage_manager.read_attachment(path, bucket_name=bucket)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with(bucket)
