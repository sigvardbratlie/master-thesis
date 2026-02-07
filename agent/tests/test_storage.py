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
        manager = SupabaseStorageManager()
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

    mock_storage_manager.save_attachment(content=content, path=path)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with("attachments")
    mock_storage_manager.supabase.storage.from_.return_value.upload.assert_called_once()

    upload_kwargs = mock_storage_manager.supabase.storage.from_.return_value.upload.call_args
    assert upload_kwargs.kwargs["path"] == path


def test_save_attachment_with_string(mock_storage_manager):
    """Test save_attachment converts string to bytes before saving."""
    content = "dette er tekstinnhold"
    path = "user123/session456/file.txt"

    mock_storage_manager.save_attachment(content=content, path=path)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with("attachments")
    mock_storage_manager.supabase.storage.from_.return_value.upload.assert_called_once()


def test_save_attachment_custom_bucket(mock_storage_manager):
    """Test save_attachment with custom bucket name."""
    content = b"some content"
    path = "user123/session456/file.pdf"
    bucket = "custom-bucket"

    mock_storage_manager.save_attachment(content=content, path=path, bucket_name=bucket)

    mock_storage_manager.supabase.storage.from_.assert_called_once_with(bucket)


def test_save_attachment_handles_error(mock_storage_manager):
    """Test save_attachment handles upload errors gracefully."""
    mock_storage_manager.supabase.storage.from_.return_value.upload.side_effect = Exception("Upload failed")
    content = b"some content"
    path = "user123/session456/file.pdf"

    # Should not raise
    mock_storage_manager.save_attachment(content=content, path=path)


# ============================================
#           save_raw_documents
# ============================================

@pytest.mark.asyncio
async def test_save_raw_documents_pdf_and_text(mock_storage_manager):
    """Test save_raw_documents processes both PDF and text attachments."""
    attachments = get_mock_attachments_list()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        await mock_storage_manager.save_raw_documents(attachments)
        assert mock_save.call_count == 2


@pytest.mark.asyncio
async def test_save_raw_documents_decodes_pdf_base64(mock_storage_manager):
    """Test that PDF content is base64-decoded before saving."""
    pdf_att = get_mock_pdf_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        await mock_storage_manager.save_raw_documents([pdf_att])

        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        content_arg = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content") or call_kwargs[0][0]
        # Content should be decoded bytes, not the original base64 string
        assert isinstance(content_arg, bytes)


@pytest.mark.asyncio
async def test_save_raw_documents_text_not_decoded(mock_storage_manager):
    """Test that text content is passed through without base64 decoding."""
    text_att = get_mock_text_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        await mock_storage_manager.save_raw_documents([text_att])

        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        content_arg = call_kwargs.kwargs.get("content") or call_kwargs[1].get("content") or call_kwargs[0][0]
        assert isinstance(content_arg, str)


@pytest.mark.asyncio
async def test_save_raw_documents_uses_correct_paths(mock_storage_manager):
    """Test that each attachment uses its own path."""
    attachments = get_mock_attachments_list()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        await mock_storage_manager.save_raw_documents(attachments)

        paths_used = [c.kwargs.get("path") or c[1].get("path") for c in mock_save.call_args_list]
        assert attachments[0].path in paths_used
        assert attachments[1].path in paths_used


@pytest.mark.asyncio
async def test_save_raw_documents_custom_bucket(mock_storage_manager):
    """Test save_raw_documents passes custom bucket name."""
    text_att = get_mock_text_attachment()

    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        await mock_storage_manager.save_raw_documents([text_att], bucket_name="custom-bucket")

        call_kwargs = mock_save.call_args
        bucket_arg = call_kwargs.kwargs.get("bucket_name") or call_kwargs[1].get("bucket_name")
        assert bucket_arg == "custom-bucket"


@pytest.mark.asyncio
async def test_save_raw_documents_empty_list(mock_storage_manager):
    """Test save_raw_documents handles empty attachment list."""
    with patch.object(mock_storage_manager, 'save_attachment') as mock_save:
        await mock_storage_manager.save_raw_documents([])
        mock_save.assert_not_called()


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
