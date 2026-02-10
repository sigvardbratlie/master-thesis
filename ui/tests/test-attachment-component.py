import pytest
import email
import base64
from io import BytesIO
from ui.ui_components.attachments import AttachmentComponent
from ui.models import AttachmentModel
from unittest.mock import MagicMock, patch, Mock
import streamlit as st


@pytest.fixture
def email_fixture():
    with open("ui/tests/fixtures/SV_ FDV GG38.eml", "r") as f:
        msg = email.message_from_file(f)
    
    return msg

@pytest.fixture
def attachment_component_fixture():
    with patch("ui.ui_components.attachments.SupabaseManager") as mock_st:
        mock_st_instance = mock_st.return_value
        mock_st_instance.get_attachment_url.return_value = "http://example.com/attachment"
        return AttachmentComponent()

def test_extract_email_body(email_fixture, attachment_component_fixture):
    msg = email_fixture

    body = attachment_component_fixture.extract_email_body(msg)
    assert "text" in body
    assert "html" in body
    assert body["text"] is not None
    assert body["html"] is not None

def test_extract_attachments(email_fixture, attachment_component_fixture):
    msg = email_fixture

    attachments = attachment_component_fixture.extract_attachments(msg)
    assert isinstance(attachments, list)
    assert len(attachments) > 0
    for att in attachments:
        assert "filename" in att
        assert "file_type" in att
        assert "size" in att
        assert "file_id" in att
        assert "content" in att
        assert att["filename"] is not None
        assert att["file_type"] is not None


def test_extract_email_data(email_fixture, attachment_component_fixture):
    msg = email_fixture

    data = attachment_component_fixture.extract_email_data(msg, query_id="test-query-123", event_id="test-event-456")
    assert "email" in data
    assert "attachments" in data
    assert data["email"].subject == "SV: FDV GG38"
    assert data["attachments"] is not None
    assert isinstance(data["attachments"], list)
    assert len(data["attachments"]) > 0
    assert data["attachments"][0].content is not None


@pytest.fixture
def mock_uploaded_file_pdf():
    """Mock PDF file"""
    mock_file = Mock()
    mock_file.name = "test_document.pdf"
    mock_file.type = "application/pdf"
    mock_file.size = 1024
    mock_file.getvalue.return_value = b"PDF content here"
    return mock_file


@pytest.fixture
def mock_uploaded_file_eml():
    """Mock EML file"""
    mock_file = Mock()
    mock_file.name = "test_email.eml"
    mock_file.type = "message/rfc822"
    mock_file.size = 2048
    # Simple EML content
    eml_content = """From: sender@example.com
To: recipient@example.com
Subject: Test Email
Date: Mon, 10 Feb 2026 12:00:00 +0000

This is a test email body.
"""
    mock_file.getvalue.return_value = eml_content.encode('utf-8')
    return mock_file


def test_mk_attachment_payload_pdf(attachment_component_fixture, mock_uploaded_file_pdf):
    """Test creating attachment payload for PDF file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_pdf, 
        query_id="test-query-123"
    )
    
    assert isinstance(result, dict)
    assert "emails" in result
    assert "attachments" in result
    assert len(result["emails"]) == 0
    assert len(result["attachments"]) == 1
    
    attachment = result["attachments"][0]
    assert isinstance(attachment, AttachmentModel)
    assert attachment.filename == "test_document.pdf"
    assert attachment.file_type == "application/pdf"
    assert attachment.size == 1024
    assert attachment.query_id == "test-query-123"
    assert attachment.file_id is not None
    assert attachment.content is not None
    # PDF should be base64 encoded
    assert isinstance(attachment.content, str)
@pytest.fixture
def mock_uploaded_file_text():
    """Mock text file"""
    mock_file = Mock()
    mock_file.name = "test_document.txt"
    mock_file.type = "text/plain"
    mock_file.size = 512
    mock_file.getvalue.return_value = b"Text content here"
    return mock_file


def test_mk_attachment_payload_text(attachment_component_fixture, mock_uploaded_file_text):
    """Test creating attachment payload for text file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_text,
        query_id="test-query-456"
    )
    
    assert isinstance(result, dict)
    assert "emails" in result
    assert "attachments" in result
    assert len(result["emails"]) == 0
    assert len(result["attachments"]) == 1
    
    attachment = result["attachments"][0]
    assert isinstance(attachment, AttachmentModel)
    assert attachment.filename == "test_document.txt"
    assert attachment.file_type == "text/plain"
    assert attachment.size == 512
    assert attachment.query_id == "test-query-456"
    assert attachment.content == "Text content here"


def test_mk_attachment_payload_eml(attachment_component_fixture, mock_uploaded_file_eml):
    """Test creating attachment payload for EML file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_eml,
        query_id="test-query-789"
    )
    
    assert isinstance(result, dict)
    assert "email" in result
    assert "attachments" in result
    
    # Should have extracted email data
    assert result["email"] is not None
    assert result["email"].subject == "Test Email"
    assert result["email"].sender == "sender@example.com"
    assert result["email"].query_id == "test-query-789"


@patch('streamlit.button')
@patch('streamlit.pdf')
@patch('streamlit.text')
@patch('streamlit.expander')
def test_view_uploaded_file_pdf(mock_expander, mock_text, mock_pdf, mock_button, 
                                 attachment_component_fixture, mock_uploaded_file_pdf):
    """Test viewing uploaded PDF file"""
    # Simulate button not clicked
    mock_button.return_value = False
    
    # Should not raise any errors
    attachment_component_fixture.view_uploaded_file(mock_uploaded_file_pdf)
    
    # Verify button was called
    assert mock_button.called


@patch('streamlit.button')
@patch('streamlit.text')
def test_view_uploaded_file_text(mock_text, mock_button, 
                                  attachment_component_fixture, mock_uploaded_file_text):
    """Test viewing uploaded text file"""
    # Simulate button click
    mock_button.return_value = True
    
    # Should not raise any errors
    attachment_component_fixture.view_uploaded_file(mock_uploaded_file_text)
    
    # Verify text was called to display content
    assert mock_text.called


@patch('streamlit.button')
@patch('streamlit.error')
def test_view_attachment_not_found(mock_error, mock_button, attachment_component_fixture):
    """Test viewing attachment when content cannot be retrieved"""
    mock_button.return_value = True
    attachment_component_fixture.database_service.read_attachment = Mock(return_value=None)
    
    attachment = {
        "file_id": "test-file-123",
        "filename": "missing.pdf",
        "file_type": "application/pdf",
        "path": "test/path/missing.pdf"
    }
    
    attachment_component_fixture.view_attachment(attachment)
    
    # Should show error
    assert mock_error.called


@patch('streamlit.button')
@patch('streamlit.pdf')
@patch('streamlit.expander')
def test_view_attachment_with_content(mock_expander, mock_pdf, mock_button, attachment_component_fixture):
    """Test viewing attachment with provided content"""
    mock_button.return_value = True
    mock_context = MagicMock()
    mock_expander.return_value.__enter__ = Mock(return_value=mock_context)
    mock_expander.return_value.__exit__ = Mock(return_value=False)
    
    attachment = {
        "file_id": "test-file-456",
        "filename": "document.pdf",
        "file_type": "application/pdf",
        "path": "test/path/document.pdf"
    }
    
    content_bytes = b"PDF content"
    
    attachment_component_fixture.view_attachment(attachment, content_bytes=content_bytes)
    
    # Should display PDF
    assert mock_pdf.called
