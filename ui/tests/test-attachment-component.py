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
    with open("ui/tests/fixtures/test-file.eml", "r") as f:
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

    data = attachment_component_fixture.extract_email_data(msg, query_id="test-query-123")
    assert "email" in data
    assert "attachments" in data
    # Check that email data was extracted from test-file.eml
    assert data["email"] is not None
    assert data["attachments"] is not None
    assert isinstance(data["attachments"], list)


@pytest.fixture
def mock_uploaded_file_pdf():
    """Mock PDF file from actual fixture file"""
    with open("ui/tests/fixtures/test-file.PDF", "rb") as f:
        file_bytes = f.read()
    
    mock_file = Mock()
    mock_file.name = "test-file.PDF"
    mock_file.type = "application/pdf"
    mock_file.size = len(file_bytes)
    mock_file.getvalue.return_value = file_bytes
    return mock_file


@pytest.fixture
def mock_uploaded_file_csv():
    """Mock CSV file from actual fixture file"""
    with open("ui/tests/fixtures/test-file.csv", "rb") as f:
        file_bytes = f.read()
    
    mock_file = Mock()
    mock_file.name = "test-file.csv"
    mock_file.type = "text/csv"
    mock_file.size = len(file_bytes)
    mock_file.getvalue.return_value = file_bytes
    return mock_file


@pytest.fixture
def mock_uploaded_file_xlsx():
    """Mock Excel file from actual fixture file"""
    with open("ui/tests/fixtures/test-file.xlsx", "rb") as f:
        file_bytes = f.read()
    
    mock_file = Mock()
    mock_file.name = "test-file.xlsx"
    mock_file.type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    mock_file.size = len(file_bytes)
    mock_file.getvalue.return_value = file_bytes
    return mock_file


@pytest.fixture
def mock_uploaded_file_docx():
    """Mock Word file from actual fixture file"""
    with open("ui/tests/fixtures/test-file.docx", "rb") as f:
        file_bytes = f.read()
    
    mock_file = Mock()
    mock_file.name = "test-file.docx"
    mock_file.type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    mock_file.size = len(file_bytes)
    mock_file.getvalue.return_value = file_bytes
    return mock_file


@pytest.fixture
def mock_uploaded_file_eml():
    """Mock EML file from actual fixture file"""
    with open("ui/tests/fixtures/test-file.eml", "rb") as f:
        file_bytes = f.read()
    
    mock_file = Mock()
    mock_file.name = "test-file.eml"
    mock_file.type = "message/rfc822"
    mock_file.size = len(file_bytes)
    mock_file.getvalue.return_value = file_bytes
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
    assert attachment.filename == "test-file.PDF"
    assert attachment.file_type == "application/pdf"
    assert attachment.size > 0
    assert attachment.query_id == "test-query-123"
    assert attachment.file_id is not None
    assert attachment.content is not None
    # PDF should be base64 encoded
    assert isinstance(attachment.content, str)
    # Verify it's valid base64
    try:
        base64.b64decode(attachment.content)
    except Exception:
        pytest.fail("PDF content is not valid base64")
def test_mk_attachment_payload_csv(attachment_component_fixture, mock_uploaded_file_csv):
    """Test creating attachment payload for CSV file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_csv,
        query_id="test-query-csv"
    )
    
    assert isinstance(result, dict)
    assert "emails" in result
    assert "attachments" in result
    assert len(result["emails"]) == 0
    assert len(result["attachments"]) == 1
    
    attachment = result["attachments"][0]
    assert isinstance(attachment, AttachmentModel)
    assert attachment.filename == "test-file.csv"
    assert attachment.file_type == "text/csv"
    assert attachment.size > 0
    assert attachment.query_id == "test-query-csv"
    assert attachment.file_id is not None
    assert attachment.content is not None
    # CSV should be decoded text (not base64)
    assert isinstance(attachment.content, str)


def test_mk_attachment_payload_xlsx(attachment_component_fixture, mock_uploaded_file_xlsx):
    """Test creating attachment payload for Excel file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_xlsx,
        query_id="test-query-xlsx"
    )
    
    assert isinstance(result, dict)
    assert "emails" in result
    assert "attachments" in result
    assert len(result["emails"]) == 0
    assert len(result["attachments"]) == 1
    
    attachment = result["attachments"][0]
    assert isinstance(attachment, AttachmentModel)
    assert attachment.filename == "test-file.xlsx"
    assert attachment.file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert attachment.size > 0
    assert attachment.query_id == "test-query-xlsx"
    assert attachment.file_id is not None
    assert attachment.content is not None
    # Excel content should be text (decoded with errors='ignore')
    assert isinstance(attachment.content, str)


def test_mk_attachment_payload_docx(attachment_component_fixture, mock_uploaded_file_docx):
    """Test creating attachment payload for Word file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_docx,
        query_id="test-query-docx"
    )
    
    assert isinstance(result, dict)
    assert "emails" in result
    assert "attachments" in result
    assert len(result["emails"]) == 0
    assert len(result["attachments"]) == 1
    
    attachment = result["attachments"][0]
    assert isinstance(attachment, AttachmentModel)
    assert attachment.filename == "test-file.docx"
    assert attachment.file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert attachment.size > 0
    assert attachment.query_id == "test-query-docx"
    assert attachment.file_id is not None
    assert attachment.content is not None
    # Word content should be text (decoded with errors='ignore')
    assert isinstance(attachment.content, str)


def test_mk_attachment_payload_eml(attachment_component_fixture, mock_uploaded_file_eml):
    """Test creating attachment payload for EML file"""
    result = attachment_component_fixture.mk_attachment_payload(
        file=mock_uploaded_file_eml,
        query_id="test-query-eml"
    )
    
    assert isinstance(result, dict)
    assert "email" in result
    assert "attachments" in result
    
    # Should have extracted email data from real EML file
    assert result["email"] is not None
    assert result["email"].subject is not None
    assert result["email"].sender is not None
    assert result["email"].query_id == "test-query-eml"
    # Email should have body text
    assert result["email"].body_text is not None
    assert isinstance(result["email"].body_text, str)


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
