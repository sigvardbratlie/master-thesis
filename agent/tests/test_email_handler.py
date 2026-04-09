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
    get_mock_eml_multipart,
    get_mock_eml_with_text_attachment,
    get_mock_eml_metadata,
    get_mock_eml_outlook_thread,
    get_mock_eml_gmail_thread,
    get_mock_write_email,
    get_mock_write_email_with_bcc,
    get_mock_eml_with_sender_names,
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from documents import EmailHandler, EmailThreadParser
from models.api_request_models import AttachmentModel, EmailModel


# ============================================
#   HELPERS FOR shorten_raw_emails TESTS
# ============================================

def _make_msg(msg_id: str, refs: str = None, date: str = "Mon, 15 Jan 2024 10:00:00 +0100") -> email.message.Message:
    """Build a minimal email.Message for thread tests."""
    msg = MIMEText("body", "plain", "utf-8")
    msg["Message-ID"] = msg_id
    msg["Date"] = date
    msg["Subject"] = "Test"
    msg["From"] = "a@b.no"
    msg["To"] = "c@d.no"
    if refs:
        msg["References"] = refs
    return email.message_from_bytes(msg.as_bytes())


# ============================================
#           FIXTURES
# ============================================

@pytest.fixture
def parser():
    return EmailHandler()


# ============================================
#           parse_eml_to_obj INPUT TESTS
# ============================================

def test_parse_eml_non_bytes_raises(parser):
    """Non-bytes content passed to parse_eml_to_obj should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid EML content"):
        parser.parse_eml_to_obj(
            content="this is a string not bytes",
            user_id="u-001",
            query_id="q-001",
            session_id="s-001",
            file_id="f-001",
        )


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
    result = parser.extract_email_data(
        msg, file_id="f-001", query_id="q-001", user_id="u-001", session_id="s-001"
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
    result = parser.extract_email_data(
        msg, file_id="f-002", query_id="q-002", user_id="u-001", session_id="s-001"
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
    result = parser.extract_email_data(
        msg, file_id="f-003", query_id="q-003", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.headers is not None
    assert isinstance(email_data.headers, dict)


def test_extract_email_data_threading_fields(parser):
    """Email threading fields should be extracted correctly."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser.extract_email_data(
        msg, file_id="f-004", query_id="q-004", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.message_id == "<test-message-id-001@juridisk.no>"
    assert email_data.in_reply_to == "<original-message-id@example.com>"
    assert email_data.thread_topic == "Eiendomssak Fjellveien 42A"


def test_extract_email_data_sender_name(parser):
    """from_name and to_names should be extracted when display names are present."""
    raw = get_mock_eml_with_sender_names()
    msg = email.message_from_bytes(raw)
    result = parser.extract_email_data(
        msg, file_id="f-n01", query_id="q-n01", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.from_name == "Advokat Hansen"
    assert email_data.from_addr == "advokat@juridisk.no"
    assert email_data.to_names is not None
    assert "Klient Olsen" in email_data.to_names
    assert "Partner Dahl" in email_data.to_names
    assert email_data.cc_names is not None
    assert "Sekretær Berg" in email_data.cc_names


def test_extract_email_data_no_display_name(parser):
    """from_name should be None when the From header contains only an email address."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser.extract_email_data(
        msg, file_id="f-n02", query_id="q-n02", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert email_data.from_name is None


def test_extract_email_data_body_text(parser):
    """Email body text should be extracted correctly."""
    raw = get_mock_eml_plain_text()
    msg = email.message_from_bytes(raw)
    result = parser.extract_email_data(
        msg, file_id="f-005", query_id="q-005", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert "eiendomssaken" in email_data.body_text


def test_extract_email_data_multipart_body(parser):
    """Multipart email should extract both text and html body."""
    raw = get_mock_eml_multipart()
    msg = email.message_from_bytes(raw)
    result = parser.extract_email_data(
        msg, file_id="f-006", query_id="q-006", user_id="u-001", session_id="s-001"
    )

    email_data = result["email"]
    assert "Befaring" in email_data.body_text
    assert email_data.body_html is not None


# ============================================
#           parse_eml TESTS
# ============================================

def test_parse_eml_valid_plain(parser):
    """Full parse of plain text EML bytes."""
    result = parser.parse_eml_to_obj(
        content=get_mock_eml_plain_text(),
        user_id="u-001",
        query_id="q-007",
        session_id="s-001",
        file_id="f-007"
    )

    assert "email" in result
    assert "attachments" in result
    assert isinstance(result["email"], EmailModel)
    assert result["email"].subject == "Re: Eiendomssak Fjellveien 42A"


def test_parse_eml_valid_with_attachment(parser):
    """Full parse of EML bytes with attachment."""
    result = parser.parse_eml_to_obj(
        content=get_mock_eml_with_text_attachment(),
        user_id="u-001",
        query_id="q-008",
        session_id="s-001",
        file_id="f-008"
    )

    assert "email" in result
    assert len(result["attachments"]) == 1
    assert result["email"].subject == "Dokumentasjon vedlagt"


def test_parse_eml_invalid_content_type(parser):
    """Non-bytes content should raise ValueError with 'Invalid EML content'."""
    with pytest.raises(ValueError, match="Invalid EML content"):
        parser.parse_eml_to_obj(
            content="!!!invalid-string-not-bytes!!!",
            user_id="u-001",
            query_id="q-009",
            session_id="s-001",
            file_id="f-009"
        )


def test_parse_eml_invalid_email_content(parser):
    """Invalid email bytes should still be handled gracefully (email module is lenient)."""
    result = parser.parse_eml_to_obj(
        content=b"This is not a valid EML file",
        user_id="u-001",
        query_id="q-010",
        session_id="s-001",
        file_id="f-010"
    )
    assert "email" in result


def test_parse_eml_multipart(parser):
    """Full parse of multipart EML bytes."""
    result = parser.parse_eml_to_obj(
        content=get_mock_eml_multipart(),
        user_id="u-001",
        query_id="q-011",
        session_id="s-001",
        file_id="f-011"
    )

    assert "email" in result
    email_data = result["email"]
    assert "Befaring" in email_data.body_text


# ============================================
#           parse_eml TESTS
# ============================================

def test_parse_eml_plain_text(parser):
    """Test parse_eml extracts text from plain text email, returning (str, dict)."""
    raw = get_mock_eml_plain_text()
    metadata = get_mock_eml_metadata()

    result = parser.parse_eml(raw, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert isinstance(text_out, str)
    assert "eiendomssaken" in text_out
    assert meta_out["file_id"] == metadata["file_id"]
    assert meta_out["session_id"] == metadata["session_id"]


def test_parse_eml_multipart_body(parser):
    """Test parse_eml extracts text from multipart email."""
    raw = get_mock_eml_multipart()
    metadata = get_mock_eml_metadata()

    result = parser.parse_eml(raw, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert "Befaring" in text_out


def test_parse_eml_with_attachment(parser):
    """Test parse_eml processes email body (not attachments)."""
    raw = get_mock_eml_with_text_attachment()
    metadata = get_mock_eml_metadata()

    result = parser.parse_eml(raw, metadata)

    assert isinstance(result, tuple)
    text_out, meta_out = result
    assert "vedlagt" in text_out.lower()


def test_parse_eml_preserves_metadata(parser):
    """Test parse_eml preserves all metadata in the returned dict."""
    raw = get_mock_eml_plain_text()
    metadata = {
        "file_id": "eml-001",
        "session_id": "s-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test-email.eml",
        "user_id": "user-123",
        "query_id": "query-456",
    }

    result = parser.parse_eml(raw, metadata)

    text_out, meta_out = result
    assert meta_out["file_id"] == "eml-001"
    assert meta_out["session_id"] == "s-001"


def test_parse_eml_invalid_bytes(parser):
    """Test parse_eml with invalid bytes returns (str, dict)."""
    metadata = get_mock_eml_metadata()
    result = parser.parse_eml(b"not a real email", metadata)
    assert isinstance(result, tuple)


# ============================================
#           EDGE CASE TESTS
# ============================================

def test_parse_eml_preserves_cc_bcc(parser):
    """CC and BCC fields should be preserved when present."""
    result = parser.parse_eml_to_obj(
        content=get_mock_eml_plain_text(),
        user_id="u-001",
        query_id="q-012",
        session_id="s-001",
        file_id="f-012"
    )

    email_data = result["email"]
    assert email_data.cc is not None
    assert "partner@juridisk.no" in email_data.cc


def test_attachment_path_format(parser):
    """Attachment paths should follow user_id/session_id/file_id.ext format."""
    result = parser.parse_eml_to_obj(
        content=get_mock_eml_with_text_attachment(),
        user_id="user-123",
        query_id="q-013",
        session_id="sess-456",
        file_id="f-013"
    )

    if result["attachments"]:
        att = result["attachments"][0]
        assert att.path.startswith("user-123/sess-456/")
        assert att.path.endswith(".txt")


# ============================================
#   reference_paths FIELD TESTS
# ============================================

def test_email_model_reference_paths_defaults_to_none(parser):
    """EmailModel.reference_paths should default to None when not set."""
    result = parser.parse_eml_to_obj(
        content=get_mock_eml_plain_text(),
        user_id="u-001",
        query_id="q-014",
        session_id="s-001",
        file_id="f-014",
    )
    email_data = result["email"]
    assert email_data.reference_paths is None


def test_email_model_reference_paths_accepts_list():
    """EmailModel.reference_paths should accept a list of path strings."""
    model = EmailModel(
        file_id="f-015",
        path="u/s/f-015.eml",
        query_id="q-015",
        subject="Test",
        from_addr="a@b.no",
        to=["c@d.no"],
        body_text="body",
        reference_paths=["u/s/attach-1.pdf", "u/s/attach-2.docx"],
    )
    assert model.reference_paths == ["u/s/attach-1.pdf", "u/s/attach-2.docx"]


# ============================================
#   shorten_raw_emails TESTS
# ============================================

def test_shorten_raw_emails_single_email(thread_parser):
    """Single email with no references should be returned as its own root."""
    msg = _make_msg("<msg-001@test.no>")
    result = thread_parser.collapse_threads({"uuid-001": msg})

    assert "uuid-001" in result
    root_msg, child_uuids = result["uuid-001"]
    assert child_uuids == set()


def test_shorten_raw_emails_thread_grouped(thread_parser):
    """Two emails in a thread should be grouped under one root entry."""
    root = _make_msg("<root@test.no>", date="Mon, 15 Jan 2024 08:00:00 +0100")
    reply = _make_msg("<reply@test.no>", refs="<root@test.no>", date="Mon, 15 Jan 2024 10:00:00 +0100")

    result = thread_parser.collapse_threads({"uuid-root": root, "uuid-reply": reply})

    assert len(result) == 1
    root_uuid, (root_email, child_uuids) = next(iter(result.items()))
    assert "uuid-reply" in child_uuids or root_uuid == "uuid-reply"


def test_shorten_raw_emails_newest_is_root(thread_parser):
    """The newest email in a thread should be selected as root (it contains all quoted content)."""
    old_msg = _make_msg("<old@test.no>", date="Mon, 15 Jan 2024 08:00:00 +0100")
    new_msg = _make_msg("<new@test.no>", refs="<old@test.no>", date="Mon, 15 Jan 2024 12:00:00 +0100")

    result = thread_parser.collapse_threads({"uuid-old": old_msg, "uuid-new": new_msg})

    root_uuid = next(iter(result))
    assert root_uuid == "uuid-new"
    _, child_uuids = result[root_uuid]
    assert "uuid-old" in child_uuids


def test_shorten_raw_emails_independent_threads(thread_parser):
    """Two unrelated emails should produce two separate root entries."""
    msg_a = _make_msg("<a@test.no>", date="Mon, 15 Jan 2024 08:00:00 +0100")
    msg_b = _make_msg("<b@test.no>", date="Mon, 15 Jan 2024 09:00:00 +0100")

    result = thread_parser.collapse_threads({"uuid-a": msg_a, "uuid-b": msg_b})

    assert len(result) == 2
    assert "uuid-a" in result
    assert "uuid-b" in result


def test_shorten_raw_emails_child_uuids_exclude_root(thread_parser):
    """Child UUID set must not include the root UUID itself."""
    root = _make_msg("<root2@test.no>", date="Mon, 15 Jan 2024 08:00:00 +0100")
    reply = _make_msg("<reply2@test.no>", refs="<root2@test.no>", date="Mon, 15 Jan 2024 10:00:00 +0100")

    result = thread_parser.collapse_threads({"uuid-r": root, "uuid-c": reply})

    root_uuid, (_, child_uuids) = next(iter(result.items()))
    assert root_uuid not in child_uuids


# ============================================
#           mk_eml TESTS
# ============================================

def test_mk_eml_creates_bytes(parser):
    """mk_eml should return bytes from a WriteEmail model."""
    write_email = get_mock_write_email()
    result = parser.mk_eml(write_email)

    assert isinstance(result, bytes)
    assert len(result) > 0


def test_mk_eml_round_trip(parser):
    """mk_eml output should be parseable and contain the original fields."""
    write_email = get_mock_write_email()
    result = parser.mk_eml(write_email)

    parsed = email.message_from_bytes(result)
    assert parsed["Subject"] == write_email.subject
    assert write_email.from_addr in parsed["From"]
    assert write_email.to[0] in parsed["To"]


def test_mk_eml_with_cc(parser):
    """mk_eml should include CC header when provided."""
    write_email = get_mock_write_email()
    result = parser.mk_eml(write_email)

    parsed = email.message_from_bytes(result)
    assert parsed["Cc"] is not None
    assert write_email.cc[0] in parsed["Cc"]


def test_mk_eml_with_bcc(parser):
    """mk_eml should include BCC header when provided."""
    write_email = get_mock_write_email_with_bcc()
    result = parser.mk_eml(write_email)

    parsed = email.message_from_bytes(result)
    assert parsed["Bcc"] is not None
    assert write_email.bcc[0] in parsed["Bcc"]


def test_mk_eml_no_cc_bcc_omits_headers(parser):
    """mk_eml should not include CC/BCC headers when they are None."""
    from models import WriteEmail
    write_email = WriteEmail(
        from_addr="sender@test.no",
        to=["recv@test.no"],
        subject="No CC",
        body="Body.",
    )
    result = parser.mk_eml(write_email)

    parsed = email.message_from_bytes(result)
    assert parsed["Cc"] is None
    assert parsed["Bcc"] is None


# ============================================
#           EmailThreadParser TESTS
# ============================================

@pytest.fixture
def thread_parser():
    return EmailThreadParser()


def test_thread_parser_clean_text_removes_quote_markers(thread_parser):
    """_clean_text should strip leading '>' characters from each line."""
    text = "> Hei\n>> Dette er sitert\n> Og dette"
    result = thread_parser._clean_text(text)
    assert ">" not in result
    assert "Hei" in result


def test_thread_parser_clean_text_removes_mailto(thread_parser):
    """_clean_text should strip <mailto:...> links."""
    text = "Kontakt oss på person@test.no <mailto:person@test.no> for spørsmål."
    result = thread_parser._clean_text(text)
    assert "<mailto:" not in result
    assert "person@test.no" in result


def test_thread_parser_extract_emails_single(thread_parser):
    """_extract_emails returns a list with a single email address."""
    result = thread_parser._extract_emails("Name Surname <email@test.no>")
    assert result == ["email@test.no"]


def test_thread_parser_extract_emails_multiple(thread_parser):
    """_extract_emails returns all addresses from a comma-separated string."""
    result = thread_parser._extract_emails("a@test.no, b@test.no; c@test.no")
    assert len(result) == 3
    assert "a@test.no" in result
    assert "b@test.no" in result
    assert "c@test.no" in result


def test_thread_parser_extract_emails_none_input(thread_parser):
    """_extract_emails returns None for None or empty input."""
    assert thread_parser._extract_emails(None) is None
    assert thread_parser._extract_emails("") is None


def test_thread_parser_normalize_date_norwegian(thread_parser):
    """normalize_date handles Norwegian date strings with 'kl.'."""
    result = thread_parser.normalize_date("5. januar 2024 kl. 10:30")
    assert result is not None
    assert "2024-01-05" in result
    assert "10:30" in result


def test_thread_parser_normalize_date_rfc2822(thread_parser):
    """normalize_date falls back to RFC 2822 parsing."""
    result = thread_parser.normalize_date("Mon, 15 Jan 2024 10:00:00 +0100")
    assert result is not None
    assert "2024" in result


def test_thread_parser_normalize_date_empty_returns_none(thread_parser):
    """normalize_date returns None for empty/None input."""
    assert thread_parser.normalize_date(None) is None
    assert thread_parser.normalize_date("") is None


def test_thread_parser_decode_eml_string_plain(thread_parser):
    """decode_eml_string returns the original string when not base64 encoded."""
    result = thread_parser.decode_eml_string("Re: Eiendomssak")
    assert result == "Re: Eiendomssak"


def test_thread_parser_decode_eml_string_base64(thread_parser):
    """decode_eml_string decodes a ?B?...?= encoded string."""
    import base64 as b64
    encoded_text = b64.b64encode("Testemne".encode("utf-8")).decode("ascii")
    subject = f"=?utf-8?B?{encoded_text}?="
    result = thread_parser.decode_eml_string(subject)
    assert result == "Testemne"


def test_thread_parser_decode_eml_string_none(thread_parser):
    """decode_eml_string returns None for None or empty input."""
    assert thread_parser.decode_eml_string(None) is None
    assert thread_parser.decode_eml_string("") is None


def test_thread_parser_parse_text_part_no_header(thread_parser):
    """parse_text_part with no header pattern returns the whole chunk as body."""
    chunk = "Dette er en enkel melding uten trådhoder."
    part = thread_parser.parse_text_part(chunk)
    assert part.body == chunk
    assert part.sender is None
    assert part.date is None


def test_thread_parser_parse_text_part_outlook_block(thread_parser):
    """parse_text_part extracts sender, date, recipient and subject from Outlook block."""
    chunk = (
        "Fra: avsender@test.no\n"
        "Dato: 5. januar 2024 kl. 10:30\n"
        "Til: mottaker@test.no\n"
        "Emne: Testmelding\n\n"
        "Innhold av meldingen."
    )
    part = thread_parser.parse_text_part(chunk)
    assert part.sender == "avsender@test.no"
    assert part.recipient is not None
    assert "mottaker@test.no" in part.recipient
    assert part.date is not None
    assert part.subject is not None


def test_thread_parser_parse_text_part_inline_pattern(thread_parser):
    """parse_text_part extracts sender and date from inline Norwegian thread pattern."""
    chunk = "5. januar 2024 kl. 10:30 skrev avsender@test.no:\n\nOpprinnelig melding."
    part = thread_parser.parse_text_part(chunk)
    assert part.date is not None
    assert "2024" in part.date


def test_thread_parser_get_email_thread_single_part(thread_parser):
    """get_email_thread returns one EmailPart for a plain email with no thread markers."""
    raw_msg = email.message_from_bytes(get_mock_eml_plain_text())
    text_part = next(p for p in raw_msg.walk() if p.get_content_type() == "text/plain")

    result = thread_parser.get_email_thread(text_part)

    assert len(result) == 1
    assert "eiendomssaken" in result[0].body.lower()


def test_thread_parser_get_email_thread_outlook(thread_parser):
    """get_email_thread splits an Outlook-threaded body into multiple parts."""
    raw_msg = email.message_from_bytes(get_mock_eml_outlook_thread())
    text_part = next(p for p in raw_msg.walk() if p.get_content_type() == "text/plain")

    result = thread_parser.get_email_thread(text_part)

    assert len(result) >= 2


def test_thread_parser_get_email_thread_gmail(thread_parser):
    """get_email_thread splits a Gmail inline thread into multiple parts."""
    raw_msg = email.message_from_bytes(get_mock_eml_gmail_thread())
    text_part = next(p for p in raw_msg.walk() if p.get_content_type() == "text/plain")

    result = thread_parser.get_email_thread(text_part)

    assert len(result) >= 2


def test_thread_parser_expand_email_backfills_date_and_subject(thread_parser):
    """expand_email backfills date and subject into the first EmailPart when missing."""
    raw_msg = email.message_from_bytes(get_mock_eml_plain_text())
    result = thread_parser.expand_email(raw_msg)

    assert len(result) >= 1
    first = result[0]
    assert first.date is not None
    assert first.subject is not None


def test_thread_parser_expand_email_first_part_has_sender(thread_parser):
    """expand_email ensures the first part has a sender (from message headers if absent)."""
    raw_msg = email.message_from_bytes(get_mock_eml_plain_text())
    result = thread_parser.expand_email(raw_msg)

    assert result[0].sender is not None


def test_thread_parser_expand_email_no_empty_lists(thread_parser):
    """expand_email converts empty recipient/cc lists to None (Pydantic safety)."""
    raw_msg = email.message_from_bytes(get_mock_eml_plain_text())
    result = thread_parser.expand_email(raw_msg)

    for part in result:
        assert part.recipient != []
        assert part.cc != []


def test_thread_parser_expand_email_outlook_thread_multiple_parts(thread_parser):
    """expand_email produces multiple parts for an Outlook-threaded email."""
    raw_msg = email.message_from_bytes(get_mock_eml_outlook_thread())
    result = thread_parser.expand_email(raw_msg)

    assert len(result) >= 2
