import streamlit as st
import pandas as pd
import hashlib
import base64
import os
import logging
from typing import Optional
from io import StringIO, BytesIO
from google.cloud import storage
from google.oauth2 import service_account
from ui.models import AttachmentModel
from streamlit.runtime.uploaded_file_manager import UploadedFile
from supabase import create_client, Client

logger = logging.getLogger(__name__)

def mk_attachment_payload(file : UploadedFile, query_id : str) -> AttachmentModel:
    file_id = hashlib.md5(file.name.encode("utf-8")).hexdigest()
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
    else:
        content = file.getvalue().decode('utf-8', errors='ignore')

    attachment = AttachmentModel(
        filename=file.name,
        file_id=file_id,
        file_type=file.type,
        path = f'{st.session_state.user_id}/{st.session_state.session_id}/{file_id}.{ext}',
        size=file.size,
        content=content,
        query_id=query_id,
    )
    return attachment


def view_uploaded_file(file : UploadedFile):
    """Display an uploaded file"""
    open_att = st.button(f"- {file.name} ({file.type}, {file.size} bytes)")
    if open_att:
        if file.type == "application/pdf":
            with st.expander(f"Viser PDF: {file.name}", expanded=True):
                st.pdf(file)
        else:
            st.text(file.getvalue().decode('utf-8', errors='ignore'))


def view_attachment(attachment: dict):
    """Display attachments from session history"""
    #st.json(attachment)
    open_att = st.button(
        f"- {attachment.get('filename')}" #- {attachment.get('file_id')} ({attachment.get('file_type')}, {attachment.get('size')} bytes)"
    )
    if open_att:
        content_bytes = read_attachment(path=attachment.get("path"), bucket_name="session_attachments")
            
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


@st.cache_data(show_spinner=False)
def _read_attachment(path : str) -> Optional[bytes]:
    """
    Fetch attachment content from GCP storage.

    Args:
        file_id: File ID (hash of filename)
        session_id: Session ID
        user_id: User ID
        type: File MIME type

    Returns:
        File content as string, or None if error
    """
    try:
        try:
            credentials = service_account.Credentials.from_service_account_info(
                st.secrets["gcp_service_account"]
            )
        except Exception as e:
            logger.error(f'Error loading service account credentials: {e}', exc_info=True)
            credentials = None

        client = storage.Client(credentials=credentials)
        bucket_name = os.getenv("BUCKET_NAME", "chat-history-files")
        blob = client.bucket(bucket_name).blob(path)

        if blob.exists():
            return blob.download_as_bytes()
        else:
            logger.error(f'Attachment blob not found: {path}')
            return None

    except Exception as e:
        logger.error(f'Error reading attachment from GCS: {e}', exc_info=True)
        return None
    

@st.cache_data(show_spinner=False)
def read_attachment(path : str, bucket_name : str = "session_attachments") -> Optional[bytes]:
    """
    Fetch attachment content from GCP storage.

    Args:
        file_id: File ID (hash of filename)
        session_id: Session ID
        user_id: User ID
        type: File MIME type

    Returns:
        File content as string, or None if error
    """
    try:
        try:
            supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
        except Exception as e:
            logger.error(f'Error loading service account credentials: {e}', exc_info=True)
            supabase = None


        content = supabase.storage.from_(bucket_name).download(path)
        if content:
            return content
        else:
            logger.error(f'Attachment blob not found: {path}')
            return ""

    except Exception as e:
        logger.error(f'Error reading attachment from Supabase: {e}', exc_info=True)
        return None

