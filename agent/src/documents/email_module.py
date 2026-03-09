import os
import logging
import base64
import uuid
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from models import VectorStoreMetadata,FileType, AttachmentModel, EmailModel, WriteEmail
import ocrmypdf
from email.message import Message
import email
from email.utils import parsedate_to_datetime
from .base_module import BaseHandler

logger = logging.getLogger(__name__)


class EmailHandler(BaseHandler):
    def __init__(self):
        super().__init__()

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
            body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
            body_html = None
        return {"html" : body_html, "text": body_text}

    def _extract_attachments(self, msg : Message) -> list:
        allowed_types = ["application/pdf", 
                         "application/msword", 
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                         "text/plain",
                         "text/csv",
                         "message/rfc822",

                         ]
        attachments = []
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition")
            if content_disposition and "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    if part.get_content_type() in allowed_types:
                        payload = part.get_payload(decode=True)
                        try:
                            content = payload.decode(part.get_content_charset() or "utf-8")
                        except (UnicodeDecodeError, LookupError):
                            content = base64.b64encode(payload).decode("ascii")
                        attachments.append({
                            "filename": filename,
                            "file_type": part.get_content_type(),
                            "size" : len(payload),
                            "file_id": str(uuid.uuid4()),
                            "content": content
                        })
                    else:
                        logger.warning(f"⚠️  Skipping attachment '{filename}' — unsupported type '{part.get_content_type()}'")
                else:
                    logger.warning("⚠️  Attachment part found without filename — skipping")
        return attachments
 
    def _extract_email_data(self, msg : Message, file_id : str, query_id : str, user_id: str , session_id : str) -> dict:
        #file_id = str(uuid.uuid4())
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
                    path = f'{user_id}/{session_id}/{att.get("file_id")}{ext}',
                )
                attachments.append(attachment_model)
                att_ids.append(att["file_id"])
        body = self._extract_email_body(msg)
        refs = msg.get("References")
        email_size = len(msg.as_bytes()) if hasattr(msg, 'as_bytes') else len(msg.as_string().encode('utf-8'))
        email_data = EmailModel(
                file_id=file_id,
                path = f'{user_id}/{session_id}/{file_id}.eml',
                query_id=query_id,

                subject=msg.get("Subject", ""),
                from_addr=msg.get("From", ""),
                to=[addr.strip() for addr in msg.get("To", "").split(",")],
                cc=[addr.strip() for addr in msg.get("Cc", "").split(",")] if msg.get("Cc") else None,
                bcc=[addr.strip() for addr in msg.get("Bcc", "").split(",")] if msg.get("Bcc") else None,
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

    def parse_eml_to_obj(self, content: bytes, user_id, query_id, session_id, file_id) -> dict:
        '''Process EML content and extract email data and attachments

        Args:
            content (bytes): The raw EML content.
            user_id (str): The ID of the user associated with the email.
            query_id (str): The ID of the query associated with the email.
            session_id (str): The ID of the session associated with the email.
            file_id (str): The ID of the file associated with the email.
        Returns:
            dict: A dictionary containing the extracted email data and attachments.

        '''
        try:
            msg = email.message_from_bytes(content)
        except Exception as e:
            logger.error(f"❌ EML parse failed: {e}", exc_info=True)
            raise ValueError("Invalid EML content") from e
        email_data = self._extract_email_data(msg, 
                                              query_id=query_id, 
                                              user_id=user_id, 
                                              session_id=session_id, 
                                              file_id=file_id)
        return email_data
    
    def parse_eml_to_docs(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> list[Document]:
        '''Process EML content and extract email data and attachments

        Args:
            content (bytes): The raw EML content.
            metadata (dict): Additional metadata to attach to each Document.
            force_metadata_model (bool): Validate and serialize metadata through VectorStoreMetadata. Defaults to True.
        Returns:
            list[Document]: A list of Document objects extracted from the email body.

        '''
        try:
            msg = email.message_from_bytes(content)
        except Exception as e:
            logger.error(f"❌ EML parse failed: {e}", exc_info=True)
            raise ValueError("Invalid EML content") from e
        body = self._extract_email_body(msg)
        chunks = self.splitter.split_text(body.get("text", ""))
        if not chunks:
            logger.warning("⚠️  No text chunks from email body — using raw text")
            chunks = [body.get("text", "")]
        metadata_all = {**metadata,
                        "file_size": len(content),
                        "file_type": "message/rfc822",
                        "creator": msg.get("From"),
                        "title": msg.get("Subject"),
                        "created_at": email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None,
                        }
        final_metadata = VectorStoreMetadata.model_validate(metadata_all).model_dump() if force_metadata_model else metadata_all
        return [
            Document(page_content=chunk, metadata={**final_metadata, "chunk": i+1, "total_chunks": len(chunks)})
            for i, chunk in enumerate(chunks)
        ]
    
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

    def shorten_raw_emails(self, emails: dict[str, Message]) -> dict[str, tuple[Message, set[str]]]:
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
    

