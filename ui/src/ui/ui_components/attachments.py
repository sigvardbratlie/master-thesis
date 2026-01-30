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
from ui.services.database_service import SupabaseManager

logger = logging.getLogger(__name__)

class AttachmentComponent:
    def __init__(self):
        self.database_service = SupabaseManager()

    def mk_attachment_payload(self, file : UploadedFile, query_id : str) -> AttachmentModel:
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


    def view_uploaded_file(self, file : UploadedFile):
        """Display an uploaded file"""
        open_att = st.button(f"- {file.name} ({file.type}, {file.size} bytes)")
        if open_att:
            if file.type == "application/pdf":
                with st.expander(f"Viser PDF: {file.name}", expanded=True):
                    st.pdf(file)
            else:
                st.text(file.getvalue().decode('utf-8', errors='ignore'))


    def view_attachment(self, attachment: dict):
        """Display attachments from session history"""
        #st.json(attachment)
        open_att = st.button(
            f"- {attachment.get('filename')}" #- {attachment.get('file_id')} ({attachment.get('file_type')}, {attachment.get('size')} bytes)"
        )
        if open_att:
            #st.info(f'Henter vedlegg: {attachment.get("path")}')
            content_bytes = self.database_service.read_attachment(path=attachment.get("path"), bucket_name="attachments")
                
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

@st.cache_resource
def get_attachment_component() -> AttachmentComponent:
    """Cached AttachmentComponent instance"""
    return AttachmentComponent()