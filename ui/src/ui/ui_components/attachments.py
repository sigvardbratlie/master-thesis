import streamlit as st
import pandas as pd
import uuid
import base64
import os
import logging
from typing import Optional
from io import StringIO, BytesIO
from google.cloud import storage
from google.oauth2 import service_account
from ui.models import AttachmentModel, EmailModel
from streamlit.runtime.uploaded_file_manager import UploadedFile
from ui.services.database_service import SupabaseManager
import email
from email.message import Message

logger = logging.getLogger(__name__)

class AttachmentComponent:
    def __init__(self):
        self.database_service = SupabaseManager()
        # Initialiser cache for vedleggsinnhold hvis ikke eksisterer
        if 'attachment_cache' not in st.session_state:
            st.session_state.attachment_cache = {}

    def mk_attachment_payload(self, file : UploadedFile, query_id : str) -> AttachmentModel:
        file_id = str(uuid.uuid4())
        ext = file.name.split('.')[-1]

        if file.type == "application/pdf":
            try:
                content = base64.b64encode(file.getvalue()).decode('utf-8')
            except UnicodeDecodeError as e:
                st.error(f'Error encoding PDF with base64: {e}')
                return None
            except Exception as e:
                st.error(f"Error encoding file {file.name}: {e}")
                return None
        elif file.type == "message/rfc822":
            try:
                content = file.getvalue().decode('utf-8', errors='ignore')
                data = self.extract_email_data(msg = email.message_from_string(content), 
                                               query_id=query_id, 
                                               )
                return data
                
            except UnicodeDecodeError as e:
                st.error(f'Error decoding EML file: {e}')
                return None
            except Exception as e:
                st.error(f"Error processing file {file.name}: {e}")
                return None
        else:
            content = file.getvalue().decode('utf-8', errors='ignore')

        # Cache vedleggsinnholdet
        cache_key = f"{st.session_state.session_id}_{file_id}"
        st.session_state.attachment_cache[cache_key] = file.getvalue()

        attachment = AttachmentModel(
            filename=file.name,
            file_id=file_id,
            file_type=file.type,
            path = f'{st.session_state.user_id}/{st.session_state.session_id}/{file_id}.{ext}',
            size=file.size,
            content=content,
            query_id=query_id,
        )
        return {"emails" : [], 
                "attachments" : [attachment]}


    def view_uploaded_file(self, file : UploadedFile):
        """Display an uploaded file - brukes for nylig opplastede filer"""
        # Generer en unik nøkkel basert på filnavn og størrelse
        file_key = f"{file.name}_{file.size}"
        
        # Cache innholdet ved første tilgang
        if file_key not in st.session_state.attachment_cache:
            st.session_state.attachment_cache[file_key] = file.getvalue()
        
        open_att = st.button(f"- {file.name} ({file.type}, {file.size} bytes)", key=f"view_{file_key}")
        
        if open_att:
            content_bytes = st.session_state.attachment_cache.get(file_key)
            
            if content_bytes:
                if file.type == "application/pdf":
                    with st.expander(f"Viser PDF: {file.name}", expanded=True):
                        st.pdf(BytesIO(content_bytes))
                else:
                    st.text(content_bytes.decode('utf-8', errors='ignore'))
            else:
                st.error(f"Kunne ikke laste innhold for {file.name}")


    def view_attachment(self, attachment: dict, content_bytes: Optional[bytes] = None, key = None):
        """Display attachments from session history"""
        file_id = attachment.get('file_id')
        cache_key = f"{st.session_state.session_id}_{file_id}"
        
        open_att = st.button(
            f"- {attachment.get('filename')}",
            key=key if key else f"att_{file_id}_{uuid.uuid4()}"
        )
        
        if open_att:
            # Sjekk cache først
            if not content_bytes:
                content_bytes = st.session_state.attachment_cache.get(cache_key)
            
            # Hvis ikke i cache, hent fra database
            if not content_bytes:
                content_bytes = self.database_service.read_attachment(
                    path=attachment.get("path"), 
                    bucket_name="attachments"
                )
                # Cache resultatet
                if content_bytes:
                    st.session_state.attachment_cache[cache_key] = content_bytes
                
            if content_bytes:
                if "pdf" in attachment.get("file_type"):
                    with st.expander(f"Viser PDF: {attachment.get('filename')}", expanded=True):
                        st.pdf(BytesIO(content_bytes))
                elif "csv" in attachment.get("file_type") or "excel" in attachment.get("file_type"):
                    try:
                        if "csv" in attachment.get("file_type"):
                            df = pd.read_csv(StringIO(content_bytes.decode('utf-8', errors='ignore')))
                        elif "excel" in attachment.get("file_type"):
                            df = pd.read_excel(BytesIO(content_bytes))
                        st.dataframe(df)
                    except Exception as e:
                        st.error(f'Kunne ikke lese fil som tabell: {e}')
                else:
                    st.text(content_bytes.decode('utf-8', errors='ignore'))
            else:
                st.error(f'Kunne ikke hente vedlegg: {attachment.get("filename")}')

    def extract_email_body(self, msg : Message) -> dict:
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

    def extract_attachments(self, msg : Message) -> list:
        attachments = []
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition")
            if content_disposition and "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachments.append({
                        "filename": filename,
                        "file_type": part.get_content_type(),
                        "size" : len(part.get_payload(decode=True)),
                        "file_id": str(uuid.uuid4()),
                        "content": base64.b64encode(part.get_payload(decode=True)).decode("utf-8")
                    })
        return attachments
 
    def extract_email_data(self, msg : Message, query_id : str, ) -> dict:
        attachments_list = self.extract_attachments(msg)
        attachments = []
        att_ids = []
        if attachments_list:
            for att in attachments_list:
                attachment_model = AttachmentModel(
                    filename=att["filename"],
                    file_id=att["file_id"],
                    file_type=att["file_type"],
                    size=att["size"],
                    content=att["content"],
                    query_id=query_id,
                    event_id=None,
                    path = f'{st.session_state.user_id}/{st.session_state.session_id}/{att["file_id"]}'
                )
                attachments.append(attachment_model)
                att_ids.append(att["file_id"])
        email_data = EmailModel(
                email_id=str(uuid.uuid4()),
                subject=msg.get("Subject", ""),
                sender=msg.get("From", ""), 
                recipients=msg.get("To", "").split(","),
                cc=msg.get("Cc", "").split(",") if msg.get("Cc") else None,
                bcc=msg.get("Bcc", "").split(",") if msg.get("Bcc") else None,
                email_date=email.utils.parsedate_to_datetime(msg.get("Date")),
                body_text=self.extract_email_body(msg).get("text", ""),
                body_html=self.extract_email_body(msg).get("html", None),
                headers=dict(msg.items()) if msg.items() else None,
                attachments= att_ids,
                query_id=query_id,
            )
    
        return {"email" : email_data, "attachments" : attachments if attachments else []}

@st.cache_resource
def get_attachment_component() -> AttachmentComponent:
    """Cached AttachmentComponent instance"""
    return AttachmentComponent()