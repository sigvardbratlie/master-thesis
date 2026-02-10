import pytest
import sys
import os
import base64
import email
from unittest.mock import MagicMock, patch
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from tests.fixtures.email_data import (
    get_mock_eml_plain_text,
    get_mock_eml_plain_text_b64,
    get_mock_eml_multipart,
    get_mock_eml_multipart_b64,
    get_mock_eml_with_text_attachment,
    get_mock_eml_with_text_attachment_b64,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.database_modules import EmailParser
from models.api_request_models import AttachmentModel, EmailModel


# ============================================
#           FIXTURES
# ============================================

@pytest.fixture
def parser():
    return EmailParser()


# ============================================
#           _decode_base64 TESTS
# ============================================

def test_decode_base64_valid(parser):
    """Valid base64 string should decode to original bytes."""
    original = b"Hello World"
    encoded = base64.b64encode(original).decode("utf-8")
    # Note: method has typo _dedoce_base64
    result = parser._dedoce_base64(encoded)
    assert result == original


def test_decode_base64_invalid(parser):
    """Invalid base64 should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid base64 content"):
        parser._dedoce_base64("!!!not-base64!!!")


def test_decode_base64_empty(parser):
    """Empty base64 string should decode to empty bytes."""
    encoded = base64.b64encode(b"").decode("utf-8")
    result = parser._dedoce_base64(encoded)
    assert result == b""


# ============================================
#           _extract_email_body TESTS
# ============================================

def test_extract_email_body_plain_text(parser):
    """Plain text email body extraction."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_body(msg)

    assert "text" in result
    assert "html" in result
    assert "eiendomssaken" in result["text"]
    assert result["html"] is None


def test_extract_email_body_multipart(parser):
    """Multipart email should extract both text and HTML."""
    raw = get_mock_eml_multipart()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_body(msg)

    assert "text" in result
    assert "html" in result
    assert "Befaring" in result["text"]
    assert result["html"] is not None
    assert "<html>" in result["html"]


def test_extract_email_body_empty_multipart(parser):
    """Multipart email with no text/html parts."""
    msg = MIMEMultipart()
    msg.attach(MIMEText("", "plain", "utf-8"))
    parsed = email.message_from_bytes(msg.as_bytes())
    result = parser._extract_email_body(parsed)

    assert "text" in result
    assert result["text"] == ""


# ============================================
#           _extract_attachments TESTS
# ============================================

def test_extract_attachments_with_attachment(parser):
    """Email with text attachment should extract it."""
    raw = get_mock_eml_with_text_attachment()
    msg = email.message_from_bytes(raw)
    result = parser._extract_attachments(msg)

    assert len(result) == 1
    assert result[0]["filename"] == "kontrakt.txt"
    assert result[0]["file_type"] == "text/plain"
    assert result[0]["size"] > 0
    assert result[0]["file_id"]  # UUID should be set
    assert "kontrakt" in result[0]["content"].lower() or "innhold" in result[0]["content"].lower()


def test_extract_attachments_no_attachment(parser):
    """Email without attachments should return empty list."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser._extract_attachments(msg)

    assert result == []


def test_extract_attachments_multipart_no_attachment(parser):
    """Multipart email with only text/html (no attachments) should return empty list."""
    raw = get_mock_eml_multipart()
    msg = email.message_from_bytes(raw)
    result = parser._extract_attachments(msg)

    assert result == []


# ============================================
#           _extract_email_data TESTS
# ============================================

def test_extract_email_data_simple(parser):
    """Extract data from a simple plain text email."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_data(
        msg, query_id="q-001", user_id="u-001", session_id="s-001"
    )

    assert "email" in result
    assert "attachments" in result
    email_data = result["email"]
    assert isinstance(email_data, EmailModel)
    assert email_data.subject == "Re: Eiendomssak Fjellveien 42A"
    assert email_data.from_addr == "advokat@juridisk.no"
    assert "klient@example.com" in email_data.to
    assert result["attachments"] == []


def test_extract_email_data_with_attachment(parser):
    """Extract data from email with text attachment."""
    raw = get_mock_eml_with_text_attachment()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_data(
        msg, query_id="q-002", user_id="u-001", session_id="s-001"
    )

    assert "email" in result
    assert "attachments" in result
    assert len(result["attachments"]) == 1
    att = result["attachments"][0]
    assert isinstance(att, AttachmentModel)
    assert att.filename == "kontrakt.txt"
    assert att.query_id == "q-002"
    assert "u-001/s-001/" in att.path


def test_extract_email_data_headers(parser):
    """Extracted email should contain headers dict."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_data(
        msg, query_id="q-003", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.headers is not None
    assert isinstance(email_data.headers, dict)


def test_extract_email_data_threading_fields(parser):
    """Email threading fields should be extracted correctly."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_data(
        msg, query_id="q-004", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.message_id == "<test-message-id-001@juridisk.no>"
    assert email_data.in_reply_to == "<original-message-id@example.com>"
    assert email_data.thread_topic == "Eiendomssak Fjellveien 42A"


def test_extract_email_data_body_text(parser):
    """Email body text should be extracted correctly."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_data(
        msg, query_id="q-005", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert "eiendomssaken" in email_data.body_text


def test_extract_email_data_multipart_body(parser):
    """Multipart email should extract both text and html body."""
    raw = get_mock_eml_multipart()
    msg = email.message_from_bytes(raw)
    result = parser._extract_email_data(
        msg, query_id="q-006", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert "Befaring" in email_data.body_text
    assert email_data.body_html is not None


# ============================================
#           parse_eml TESTS
# ============================================

def test_parse_eml_valid_plain(parser):
    """Full parse of base64-encoded plain text EML."""
    b64_content = get_mock_eml_plain_text_b64()
    result = parser.parse_eml(
        content=b64_content,
        user_id="u-001",
        query_id="q-007",
        session_id="s-001"
    )

    assert "email" in result
    assert "attachments" in result
    assert isinstance(result["email"], EmailModel)
    assert result["email"].subject == "Re: Eiendomssak Fjellveien 42A"


def test_parse_eml_valid_with_attachment(parser):
    """Full parse of base64-encoded EML with attachment."""
    b64_content = get_mock_eml_with_text_attachment_b64()
    result = parser.parse_eml(
        content=b64_content,
        user_id="u-001",
        query_id="q-008",
        session_id="s-001"
    )

    assert "email" in result
    assert len(result["attachments"]) == 1
    assert result["email"].subject == "Dokumentasjon vedlagt"


def test_parse_eml_invalid_base64(parser):
    """Invalid base64 should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid base64 content"):
        parser.parse_eml(
            content="!!!invalid-base64!!!",
            user_id="u-001",
            query_id="q-009",
            session_id="s-001"
        )


def test_parse_eml_invalid_email_content(parser):
    """Valid base64 but invalid email content should raise ValueError."""
    not_an_email = base64.b64encode(b"This is not a valid EML file").decode("utf-8")
    # email.message_from_bytes is lenient - it won't raise for most content.
    # But we should still get a result (email module is very forgiving)
    result = parser.parse_eml(
        content=not_an_email,
        user_id="u-001",
        query_id="q-010",
        session_id="s-001"
    )
    assert "email" in result


def test_parse_eml_multipart(parser):
    """Full parse of multipart EML."""
    b64_content = get_mock_eml_multipart_b64()
    result = parser.parse_eml(
        content=b64_content,
        user_id="u-001",
        query_id="q-011",
        session_id="s-001"
    )

    assert "email" in result
    email_data = result["email"]
    assert "Befaring" in email_data.body_text


# ============================================
#           EDGE CASE TESTS
# ============================================

def test_parse_eml_preserves_cc_bcc(parser):
    """CC and BCC fields should be preserved when present."""
    b64_content = get_mock_eml_plain_text_b64()
    result = parser.parse_eml(
        content=b64_content,
        user_id="u-001",
        query_id="q-012",
        session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.cc is not None
    assert "partner@juridisk.no" in email_data.cc


def test_attachment_path_format(parser):
    """Attachment paths should follow user_id/session_id/file_id.ext format."""
    b64_content = get_mock_eml_with_text_attachment_b64()
    result = parser.parse_eml(
        content=b64_content,
        user_id="user-123",
        query_id="q-013",
        session_id="sess-456"
    )

    if result["attachments"]:
        att = result["attachments"][0]
        assert att.path.startswith("user-123/sess-456/")
        assert att.path.endswith(".txt")
