import os
import logging
import base64
import uuid
import re
import html as html_lib

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from models import VectorStoreMetadata,FileType, AttachmentModel, EmailModel, WriteEmail
import ocrmypdf
from email.message import Message
import email
from email.utils import parsedate_to_datetime
from .base_module import BaseHandler
import re
from typing import Optional, List
from pydantic import BaseModel, Field
from email.utils import parseaddr, parsedate_to_datetime
from email.header import decode_header, make_header
from base64 import b64decode
from email.message import Message
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailBaseClass(BaseHandler):
    def __init__(self,chunk_size : int = 1000, chunk_overlap : int = 200):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"^>+", "", text, flags=re.MULTILINE)
        return re.sub(r"<mailto:[^>]+>", "", text).strip()

    def _strip_html(self, html_text: str) -> str:
        # Remove <style> and <script> blocks including their content
        text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html_text, flags=re.IGNORECASE | re.DOTALL)
        # Replace block-level tags with newlines to preserve paragraph structure
        text = re.sub(r"<(?:br|p|div|tr|li|hr|blockquote)(?:\s[^>]*)?>", "\n", text, flags=re.IGNORECASE)
        # Strip all remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities (&nbsp; &lt; &amp; etc.)
        text = html_lib.unescape(text)
        # Collapse multiple blank lines into one
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def decode_eml_string(self, text: str | None) -> str | None:
        if not text: return None
        try:
            decoded = str(make_header(decode_header(text))).strip()
            return decoded if decoded else None
        except:
            return text.strip()


class EmailHandler(EmailBaseClass):
    def __init__(self,chunk_size : int = 1000, chunk_overlap : int = 200):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def _extract_email_body(self, msg : Message) -> dict:
        if msg.is_multipart():
            body_text = ""
            body_html = None
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body_text += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
                elif content_type == "text/html":
                    body_html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
        else:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                body_html = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
                body_text = ""
            else:
                body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
                body_html = None

        # Fallback: derive plain text from HTML when text/plain is absent
        if not body_text.strip() and body_html:
            body_text = self._strip_html(body_html)

        return {"html": body_html, "text": self._clean_text(body_text)}

    def _resolve_content_type(self, part) -> str:
        EXTENSION_TYPE_MAP = {
                            ".eml": "message/rfc822",
                            ".pdf": "application/pdf",
                            ".doc": "application/msword",
                            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            ".txt": "text/plain",
                            ".csv": "text/csv",
                        }
        content_type = part.get_content_type()
        if content_type == "application/octet-stream":
            filename = part.get_filename() or ""
            ext = os.path.splitext(filename)[1].lower()
            return EXTENSION_TYPE_MAP.get(ext, content_type)
        return content_type

    def _extract_attachments(self, msg : Message) -> list:
        allowed_types = ["application/pdf", 
                            "application/msword", 
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "text/plain",
                            "text/csv",
                            "message/rfc822",
                            'application/octet-stream',
                            ]
        attachments = []
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition")
            if content_disposition and "attachment" in content_disposition:
                filename = part.get_filename()
                file_type = part.get_content_type()
                if filename:
                    if file_type in allowed_types:
                        payload = part.get_payload(decode=True)
                        if file_type == "application/octet-stream":
                            file_type = self._resolve_content_type(part)
                            content = payload
                        else:
                            try:
                                content = payload.decode(part.get_content_charset() or "utf-8")
                            except (UnicodeDecodeError, LookupError):
                                content = base64.b64encode(payload).decode("ascii")
                        attachments.append({
                            "filename": filename,
                            "file_type": file_type,
                            "size" : len(payload),
                            "file_id": str(uuid.uuid4()),
                            "content": content
                        })
                    else:
                        logger.warning(f"⚠️  Skipping attachment '{filename}' — unsupported type '{file_type}'")
                else:
                    logger.warning("⚠️  Attachment part found without filename — skipping")
        return attachments
 
    def extract_email_data(self, msg : Message, file_id : str, query_id : str, user_id: str, path: str) -> dict:
        """Extract email data and nested attachments from a parsed email message.

        Args:
            path: Full GCS path for this email (e.g. '{user_id}/{project_id}/{file_id}.eml').
                  Nested attachment paths are derived using the same directory prefix.
        """
        base_dir = os.path.dirname(path)
        attachments_list = self._extract_attachments(msg)
        attachments = []
        att_ids = []
        if attachments_list:
            for att in attachments_list:
                ext = os.path.splitext(att["filename"])[1].lower()
                attachment_model = AttachmentModel(
                    filename=att["filename"],
                    file_id=att["file_id"],
                    file_type=att["file_type"],
                    size=att["size"],
                    content=att["content"],
                    query_id=query_id,
                    event_id=None,
                    path=f'{base_dir}/{att.get("file_id")}{ext}',
                )
                attachments.append(attachment_model)
                att_ids.append(att["file_id"])
        body = self._extract_email_body(msg)
        refs = msg.get("References")
        email_size = len(msg.as_bytes()) if hasattr(msg, 'as_bytes') else len(msg.as_string().encode('utf-8'))
        parsed_from = parseaddr(msg.get("From", ""))
        parsed_to = [parseaddr(addr) for addr in msg.get("To", "").split(",")]
        parsed_cc = [parseaddr(addr) for addr in msg.get("Cc", "").split(",")] if msg.get("Cc") else []
        parsed_bcc = [parseaddr(addr) for addr in msg.get("Bcc", "").split(",")] if msg.get("Bcc") else []
        email_data = EmailModel(
                file_id=file_id,
                path = path,
                query_id=query_id,

                subject=self.decode_eml_string(msg.get("Subject", "")),
                from_addr=parsed_from[1],
                from_name=parsed_from[0] or None,
                to=[addr[1] for addr in parsed_to],
                to_names=[name for name, _ in parsed_to if name] or None,
                cc=[addr[1] for addr in parsed_cc] if msg.get("Cc") else None,
                cc_names=[name for name, _ in parsed_cc if name] if msg.get("Cc") else None,
                bcc=[addr[1] for addr in parsed_bcc] if msg.get("Bcc") else None,
                bcc_names=[name for name, _ in parsed_bcc if name] if msg.get("Bcc") else None,
                date=email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None,

                message_id=msg.get("Message-ID"),
                in_reply_to=msg.get("In-Reply-To"),
                references=refs,
                thread_id=msg.get("Thread-ID"),
                thread_index=msg.get("Thread-Index"),
                thread_topic=msg.get("Thread-Topic"),

                body_text=body.get("text", ""),
                body_html=body.get("html"),
                headers=dict(msg.items()) if msg.items() else None,
                size=email_size,

                attachments=att_ids if att_ids else None,
            )

        return {"email" : email_data, "attachments" : attachments if attachments else []}

    def parse_eml_to_obj(self, content: bytes, user_id, query_id, path, file_id) -> dict:
        '''Process EML content and extract email data and attachments

        Args:
            content (bytes): The raw EML content.
            user_id (str): The ID of the user associated with the email.
            query_id (str): The ID of the query associated with the email.
            path (str): Full GCS path for this email (e.g. '{user_id}/{project_id}/{file_id}.eml').
            file_id (str): The ID of the file associated with the email.
        Returns:
            dict: A dictionary containing the extracted email data and attachments.

        '''
        try:
            msg = email.message_from_bytes(content)
        except Exception as e:
            logger.exception(f"❌ EML parse failed")
            raise ValueError("Invalid EML content") from e
        email_data = self.extract_email_data(msg,
                                             query_id=query_id,
                                             user_id=user_id,
                                             path=path,
                                             file_id=file_id)
        return email_data
    
    def parse_eml(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> tuple[str, dict]:
        '''Process EML content and extract email data and attachments

        Args:
            content (bytes): The raw EML content.
            metadata (dict): Additional metadata to attach to each Document.
            force_metadata_model (bool): Validate and serialize metadata through VectorStoreMetadata. Defaults to True.
        Returns:
            tuple[str, dict]: A tuple containing the extracted email body text and metadata.

        '''
        try:
            msg = email.message_from_bytes(content)
        except Exception as e:
            logger.exception(f"❌ EML parse failed")
            raise ValueError("Invalid EML content") from e
        body = self._extract_email_body(msg)
        metadata_all = {**metadata,
                        "file_size": len(content),
                        "file_type": "message/rfc822",
                        "creator": msg.get("From"),
                        "title": msg.get("Subject"),
                        "created_at": email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None,
                        }
        final_metadata = VectorStoreMetadata.model_validate(metadata_all).model_dump(mode="json") if force_metadata_model else metadata_all
        return body.get("text", ""), final_metadata

    def mk_eml(self, email_data : WriteEmail) -> bytes:
        msg = email.message.EmailMessage()
        msg["Subject"] = email_data.subject
        msg["From"] = email_data.from_addr
        msg["To"] = ", ".join(email_data.to)
        if email_data.cc:
            msg["Cc"] = ", ".join(email_data.cc)
        if email_data.bcc:
            msg["Bcc"] = ", ".join(email_data.bcc)
        msg.set_content(email_data.body)
        return msg.as_bytes()

    
    
class EmailPart(BaseModel):
    sender: Optional[str] = Field(None, alias="from")
    recipient: Optional[List[str]] = Field(None, alias="to")
    cc: Optional[List[str]] = None
    date: Optional[str] = None
    subject: Optional[str] = None
    body: str

    class Config:
        populate_by_name = True

class EmailThreadParser(EmailBaseClass):
    def __init__(self):
        # BLOCK: Outlook-stil
        self.block_pattern = re.compile(
            r"\*?(?:Fra|From)\s*\*?:\s*\*?(?P<from>.*?)\s*"
            r"\*?(?:Sendt|Dato|Date)\s*\*?:\s*\*?(?P<date>.*?)\s*"
            r"\*?(?:Til|To)\s*\*?:\s*\*?(?P<to>.*?)\s*"
            r"(?:\*?(?:Kopi|Cc)\s*\*?:\s*\*?(?P<cc>.*?)\s*)?"
            r"\*?(?:Emne|Subject)\s*\*?:\s*\*?(?P<subject>.*?)(?=\r|\n|$)", 
            re.IGNORECASE
        )
        
        # INLINE: Gmail/Mobil/Yahoo norsk-stil ("3. mars 2026 kl. 10:24" eller "kl. 10:24:00 CET")
        self.inline_pattern = re.compile(
            r"(?P<date>\d{1,2}\.\s+\w+\.?\s+\d{4}\s+kl\.\s+\d{2}:\d{2}(?::\d{2})?(?:\s+\w+)?)\s+skrev\s+(?P<from>.*?):",
            re.IGNORECASE
        )

        # INLINE: Gmail/Yahoo/AOL engelsk-stil
        self.gmail_en_pattern = re.compile(
            r"On\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+(?P<date>\w+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM))\s+(?P<from>.*?)\s+wrote:",
            re.IGNORECASE
        )

        self.norwegian_months = {
            'jan': 1, 'januar': 1, 'feb': 2, 'februar': 2, 'mar': 3, 'mars': 3,
            'apr': 4, 'april': 4, 'mai': 5, 'jun': 6, 'juni': 6, 'jul': 7, 'juli': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'okt': 10, 'oktober': 10,
            'nov': 11, 'november': 11, 'des': 12, 'desember': 12
        }

        self.english_months = {
            'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
            'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
            'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'oct': 10, 'october': 10,
            'nov': 11, 'november': 11, 'dec': 12, 'december': 12
        }

    def _extract_emails(self, text: str | None) -> Optional[List[str]]:
        if not text: return None
        emails = []
        for p in re.split(r'[;,]', text.replace('\n', ' ')):
            _, addr = parseaddr(p.strip())
            if addr:
                emails.append(addr.lower())
            elif '@' in p and (match := re.search(r'[\w\.-]+@[\w\.-]+', p)):
                emails.append(match.group().lower())
        return emails if emails else None

    def normalize_date(self, date_str: str) -> str:
        if not date_str: return None
        date_str = date_str.replace('*', '').strip()
        
        # Norwegian format: "3. mars 2026 kl. 10:24"
        no_pattern = re.compile(
            r"(?:[a-zæøå]+,\s*)?(?P<day>\d{1,2})\.\s*(?P<month>[a-zæøå]+)\.?\s*(?P<year>\d{4})\s*(?:kl\.)?\s*(?P<hour>\d{2}):(?P<minute>\d{2})",
            re.IGNORECASE
        )
        if match := no_pattern.search(date_str):
            m_str = match.group('month').lower()
            m_num = self.norwegian_months.get(m_str, self.norwegian_months.get(m_str[:3], 1))
            try:
                return datetime(int(match.group('year')), m_num, int(match.group('day')),
                                int(match.group('hour')), int(match.group('minute'))).isoformat()
            except: pass

        # English format: "Mar 2, 2026 at 10:39 AM"
        en_pattern = re.compile(
            r"(?P<month>[a-z]+)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})\s+at\s+(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>AM|PM)",
            re.IGNORECASE
        )
        if match := en_pattern.search(date_str):
            m_str = match.group('month').lower()
            m_num = self.english_months.get(m_str, self.english_months.get(m_str[:3], 1))
            hour = int(match.group('hour'))
            ampm = match.group('ampm').upper()
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0
            try:
                return datetime(int(match.group('year')), m_num, int(match.group('day')),
                                hour, int(match.group('minute'))).isoformat()
            except: pass

        try:
            return parsedate_to_datetime(date_str).isoformat()
        except: return date_str


    def parse_text_part(self, chunk: str) -> EmailPart:
        chunk = self._clean_text(chunk)
        
        if match := self.block_pattern.search(chunk):
            meta = match.groupdict()
            body = chunk[match.end():].strip()
        elif match := self.inline_pattern.search(chunk):
            meta = match.groupdict()
            body = chunk[match.end():].strip()
        elif match := self.gmail_en_pattern.search(chunk):
            meta = match.groupdict()
            body = chunk[match.end():].strip()
        else:
            meta = {}
            body = chunk

        sender_list = self._extract_emails(meta.get("from"))
        
        return EmailPart(
            sender=sender_list[0] if sender_list else None,
            recipient=self._extract_emails(meta.get("to")),
            cc=self._extract_emails(meta.get("cc")),
            date=self.normalize_date(meta.get("date")),
            subject=meta.get("subject").strip() if meta.get("subject") else None,
            body=body
        )

    def get_raw_text(self, part: Message) -> str:
        payload = part.get_payload(decode=True)
        if not payload: return []
        
        raw_text = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        return raw_text

    def get_email_thread(self, raw_text : str ) -> List[EmailPart]:
        
        
        PATTERNS = [
            r"\d{1,2}\.\s+\w+\.?\s+\d{4}\s+kl\.\s+\d{2}:\d{2}(?::\d{2})?(?:\s+\w+)?\s+skrev\s+.*?:",
            r"\*?(?:Fra|From)\s*\*?:\s*.*?\s*\*?(?:Sendt|Dato|Date)\s*\*?:",
            r"[ \t]*On\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\w+\s+\d{1,2},\s+\d{4}\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM)\s+.*?wrote:",
        ]
        
        parts = re.split(f"({'|'.join(PATTERNS)})", raw_text, flags=re.IGNORECASE)
        
        if len(parts) <= 1:
            return [self.parse_text_part(raw_text)]

        thread = [self.parse_text_part(parts[0])]
        for i in range(1, len(parts), 2):
            thread.append(self.parse_text_part(parts[i] + parts[i+1]))

        return thread

    def expand_email(self, msg: Message) -> List[EmailPart]:
        # 1. Hent ut alle tråd-deler
        results = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    raw_text = self.get_raw_text(part)
                elif part.get_content_type() == "text/html":
                    raw_text = self._strip_html(self.get_raw_text(part))
                else:
                    continue
                results.extend(self.get_email_thread(raw_text=raw_text))
        else:
            if msg.get_content_type() == "text/plain":
                raw_text = self.get_raw_text(msg)
            elif msg.get_content_type() == "text/html":
                raw_text = self._strip_html(self.get_raw_text(msg))
            else:
                return []
            results.extend(self.get_email_thread(raw_text=raw_text))
                
        if not results:
            return []

        # 2. Trekk ut hoved-metadata én gang
        raw_date = msg.get("Date")
        parsed_date = parsedate_to_datetime(raw_date) if raw_date else None
        main_date = parsed_date.isoformat() if parsed_date else raw_date
        
        main_sender = parseaddr(msg.get("From"))[1] if msg.get("From") else None
        main_recipients = self._extract_emails(msg.get("To")) or []
        main_cc = self._extract_emails(msg.get("Cc")) or []
        main_subject = self.decode_eml_string(msg.get("Subject"))
        
        main_sender_low = main_sender.lower() if main_sender else ""
        main_recipients_low = [r.lower() for r in main_recipients]

        # 3. Backfill logikk for tråden
        for i, part in enumerate(results):
            if i == 0:
                part.sender = part.sender or main_sender
            
            curr_sender = part.sender.lower() if part.sender else ""
            
            # Boolsk logikk for å gjøre koden lesbar
            is_first = (i == 0)
            is_main_sender = (curr_sender == main_sender_low)
            is_main_recipient = (curr_sender in main_recipients_low)

            if is_first or is_main_sender or is_main_recipient:
                # Fyll inn manglende felles-data
                part.date = part.date or main_date
                part.subject = part.subject or main_subject
                part.cc = part.cc or (main_cc if main_cc else None)

                # Avgjør hvem som er mottaker basert på hvem som sendte svaret
                if is_first or is_main_sender:
                    part.recipient = part.recipient or (main_recipients if main_recipients else None)
                elif is_main_recipient:
                    part.recipient = part.recipient or ([main_sender] if main_sender else None)

            # Sikre at tomme lister blir None for Pydantic
            part.recipient = part.recipient or None
            part.cc = part.cc or None

        return results
    
    def collapse_threads(self, emails: dict[str, Message]) -> dict[str, tuple[Message, set[str]]]:
        """Extracts the root email from a thread and lists all related file_uuids.
        
        Args:
            emails: A dictionary mapping file UUIDs to email Message objects.
        Returns:
            A dictionary mapping the root email's file UUID to a tuple containing the root email Message and a set of file UUIDs that are part of the same thread (excluding the root).
        """
        
        threads_by_root = {}
        
        for file_uuid, email in emails.items():
            msg_id = email.get("Message-ID")
            refs_str = email.get("References", "") or ""
            ref_list = [r.strip() for r in re.split(r'\s+', refs_str) if r.strip()]
            
            root_msg_id = ref_list[0] if ref_list else msg_id
            
            threads_by_root.setdefault(root_msg_id, []).append((file_uuid, email))
            
        result = {}
        
        for root_msg_id, thread_items in threads_by_root.items():
            
            sorted_thread = sorted(thread_items, key=lambda x: parsedate_to_datetime(x[1].get("Date")))

            root_uuid, root_email = sorted_thread[-1]  # newest contains all quoted content

            child_uuids = {uuid for uuid, _ in sorted_thread if uuid != root_uuid}
            
            result[root_uuid] = (root_email, child_uuids)
            
        return result
    
    