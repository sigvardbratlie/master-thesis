import base64
import email
from email import policy
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime

from models import EmailModel, EmailExtracted, Email


# ============================================
#           EML CONTENT GENERATORS
# ============================================

def get_mock_eml_plain_text() -> bytes:
    """Simple plain text EML as raw bytes."""
    msg = MIMEText("Hei, dette er en test-email angående eiendomssaken.", "plain", "utf-8")
    msg["Subject"] = "Re: Eiendomssak Fjellveien 42A"
    msg["From"] = "advokat@juridisk.no"
    msg["To"] = "klient@example.com"
    msg["Cc"] = "partner@juridisk.no"
    msg["Date"] = "Mon, 15 Jan 2024 10:30:00 +0100"
    msg["Message-ID"] = "<test-message-id-001@juridisk.no>"
    msg["In-Reply-To"] = "<original-message-id@example.com>"
    msg["Thread-Topic"] = "Eiendomssak Fjellveien 42A"
    return msg.as_bytes()


def get_mock_eml_plain_text_b64() -> str:
    """Simple plain text EML as base64 encoded string."""
    return base64.b64encode(get_mock_eml_plain_text()).decode("utf-8")


def get_mock_eml_multipart() -> bytes:
    """Multipart EML with text and HTML as raw bytes."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Oppdatering: Befaring Fjellveien 42A"
    msg["From"] = "takstmann@protakst.no"
    msg["To"] = "advokat@juridisk.no, klient@example.com"
    msg["Date"] = "Wed, 20 Jan 2024 14:00:00 +0100"
    msg["Message-ID"] = "<test-message-id-002@protakst.no>"

    text_part = MIMEText("Befaring gjennomført. Se vedlagt rapport.", "plain", "utf-8")
    html_part = MIMEText(
        "<html><body><p>Befaring gjennomf&oslash;rt. Se vedlagt rapport.</p></body></html>",
        "html", "utf-8"
    )
    msg.attach(text_part)
    msg.attach(html_part)
    return msg.as_bytes()


def get_mock_eml_multipart_b64() -> str:
    """Multipart EML as base64 encoded string."""
    return base64.b64encode(get_mock_eml_multipart()).decode("utf-8")


def get_mock_eml_with_text_attachment() -> bytes:
    """Multipart EML with a text file attachment as raw bytes."""
    msg = MIMEMultipart("mixed")
    msg["Subject"] = "Dokumentasjon vedlagt"
    msg["From"] = "advokat@juridisk.no"
    msg["To"] = "klient@example.com"
    msg["Date"] = "Fri, 25 Jan 2024 09:00:00 +0100"
    msg["Message-ID"] = "<test-message-id-003@juridisk.no>"

    body = MIMEText("Se vedlagt dokument for detaljer.", "plain", "utf-8")
    msg.attach(body)

    attachment_content = "Innhold av vedlegget: kontrakt detaljer for Fjellveien 42A."
    attachment = MIMEText(attachment_content, "plain", "utf-8")
    attachment.add_header("Content-Disposition", "attachment", filename="kontrakt.txt")
    msg.attach(attachment)
    return msg.as_bytes()


def get_mock_eml_with_text_attachment_b64() -> str:
    """EML with text attachment as base64 encoded string."""
    return base64.b64encode(get_mock_eml_with_text_attachment()).decode("utf-8")


def get_mock_eml_no_date() -> bytes:
    """EML without Date header."""
    msg = MIMEText("En email uten dato-header.", "plain", "utf-8")
    msg["Subject"] = "Test uten dato"
    msg["From"] = "avsender@test.no"
    msg["To"] = "mottaker@test.no"
    msg["Message-ID"] = "<test-no-date@test.no>"
    return msg.as_bytes()


# ============================================
#           MOCK MODELS
# ============================================

def get_mock_email_model() -> EmailModel:
    """A valid EmailModel for testing."""
    return EmailModel(
        file_id="test-file-id-001",
        path="test-user/test-session/test-file-id-001.eml",
        query_id="test-query-id-001",
        event_id=None,
        subject="Re: Eiendomssak Fjellveien 42A",
        from_addr="advokat@juridisk.no",
        to=["klient@example.com"],
        cc=["partner@juridisk.no"],
        bcc=None,
        date=datetime(2024, 1, 15, 10, 30, 0),
        message_id="<test-message-id-001@juridisk.no>",
        in_reply_to="<original-message-id@example.com>",
        references=None,
        thread_topic="Eiendomssak Fjellveien 42A",
        thread_index=None,
        thread_id=None,
        body_text="Hei, dette er en test-email angående eiendomssaken.",
        body_html=None,
        headers=None,
        attachments=None,
    )


def load_real_test_email() -> EmailModel:
    """Load the actual test-file.eml and convert to EmailModel"""
    eml_path = Path(__file__).parent / "test-file.eml"
    
    with open(eml_path, 'rb') as f:
        msg = email.message_from_binary_file(f, policy=policy.default)
    
    # Extract email data
    date_parsed = None
    if msg.get('Date'):
        try:
            date_parsed = parsedate_to_datetime(msg.get('Date'))
        except Exception:
            pass
    
    # Get body text
    body_text = ""
    body_html = None
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain' and not body_text:
                try:
                    body_text = part.get_content()
                except Exception:
                    body_text = str(part.get_payload(decode=True), 'utf-8', errors='ignore')
            elif content_type == 'text/html' and not body_html:
                try:
                    body_html = part.get_content()
                except Exception:
                    body_html = str(part.get_payload(decode=True), 'utf-8', errors='ignore')
    else:
        try:
            body_text = msg.get_content()
        except Exception:
            body_text = str(msg.get_payload(decode=True), 'utf-8', errors='ignore')
    
    return EmailModel(
        file_id="real-test-file-eml-001",
        path="test-user/test-session/test-file.eml",
        query_id="real-test-query-001",
        event_id=None,
        subject=msg.get('Subject', ''),
        from_addr=msg.get('From', ''),
        to=[msg.get('To', '')] if msg.get('To') else [],
        cc=[msg.get('Cc')] if msg.get('Cc') else None,
        bcc=[msg.get('Bcc')] if msg.get('Bcc') else None,
        date=date_parsed,
        message_id=msg.get('Message-ID'),
        in_reply_to=msg.get('In-Reply-To'),
        references=msg.get('References'),
        thread_topic=msg.get('Thread-Topic'),
        thread_index=msg.get('Thread-Index'),
        thread_id=None,
        body_text=body_text or "(No text body)",
        body_html=body_html,
        headers={k: v for k, v in msg.items()},
        attachments=None,
    )


def get_mock_email_model_list() -> list[EmailModel]:
    """List of EmailModels for batch analysis testing."""
    return [
        get_mock_email_model(),
        EmailModel(
            file_id="test-file-id-002",
            path="test-user/test-session/test-file-id-002.eml",
            query_id="test-query-id-002",
            event_id=None,
            subject="Oppdatering: Befaring Fjellveien 42A",
            from_addr="takstmann@protakst.no",
            to=["advokat@juridisk.no", "klient@example.com"],
            cc=None,
            bcc=None,
            date=datetime(2024, 1, 20, 14, 0, 0),
            message_id="<test-message-id-002@protakst.no>",
            in_reply_to=None,
            references=None,
            thread_topic=None,
            thread_index=None,
            thread_id=None,
            body_text="Befaring gjennomført. Se vedlagt rapport.",
            body_html=None,
            headers=None,
            attachments=None,
        ),
    ]


def get_mock_email_extracted() -> EmailExtracted:
    """A mock EmailExtracted result from LLM analysis."""
    return EmailExtracted(
        description="Email about property case updates for Fjellveien 42A",
        significance="high",
        party_roles=["plaintiff", "legal_rep_plaintiff"],
        deadlines=None,
        damages=None,
        claims=None,
        key_points=["Befaring planlagt", "Rapport vedlagt"],
        email_id="test-email-extracted-001",
    )


def get_mock_eml_metadata() -> dict:
    """Standard metadata for EML document processing."""
    return {
        "file_id": "eml-file-id-001",
        "session_id": "eml-session-id-001",
        "embedding_model": "google_gemini-embedding-001",
        "filename": "test-email.eml",
        "user_id": "user-123",
        "query_id": "query-456",
    }
