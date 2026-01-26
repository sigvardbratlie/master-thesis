import asyncio
import token
from typing import Optional, Literal
import os
from io import BytesIO
from PyPDF2 import PdfReader
import logging
import base64

from langchain_core.messages import SystemMessage
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore


from google.cloud import bigquery
from google.cloud import storage
from google.cloud import bigquery

from agent.basemodels import *
from supabase import create_client, Client
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GCSManager:

    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "chat-history-files")
        self.bucket = self.client.bucket(self.bucket_name)
    
    async def save_attachment(self,content : bytes, path : str):
        try:
            blob = self.bucket.blob(path)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.upload_from_string, content)
            logger.info(f"Attachment saved to GCS at {path}")
        except Exception as e:
            logger.error(f"Error saving attachment to GCS: {e}")

    async def save_raw_documents(self, attachments: list[AttachmentModel], bucket_name: str = "session_attachments"):
        """Lagrer alle vedlegg parallelt"""
        tasks = []
        
        for att in attachments:
            # meta = {
            #     "filename": att.filename,
            #     "file_id": att.file_id,
            #     "user_id": user_id,
            #     "session_id": session_id,
            #     'query_id': query_id,
            #     "source_type": att.file_type,
            #     "uploaded_at": datetime.now().isoformat(),
            # }
            content = att.content
            
            # Decode content
            if att.file_type == "application/pdf":
                content_bytes = base64.b64decode(content)
                tasks.append(self.save_attachment(content_bytes, path=att.path, bucket_name=bucket_name))
            else:
                tasks.append(self.save_attachment(content, path=att.path, bucket_name=bucket_name))
        
        # Kjør alle uploads parallelt
        await asyncio.gather(*tasks)

class SupabaseStorageManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)

    def save_attachment(self, content: bytes, path : str, bucket_name: str = "session_attachments"):
        try:
            self.supabase.storage.from_(bucket_name)\
                .upload(file = content, 
                        path = path, 
                        file_options={"cache-control" : "3600"})
            logger.info(f"Attachment saved to Supabase Storage at {path}")
        except Exception as e:
            logger.error(f"Error saving attachment to Supabase Storage: {e}")
            

    async def save_raw_documents(self, attachments: list[AttachmentModel], bucket_name: str = "session_attachments"):
        tasks = []

        for att in attachments:
            path = att.path
            if att.file_type == "application/pdf":
                content_bytes = base64.b64decode(att.content)
            else:
                content_bytes = att.content

            # Kjør blocking I/O i thread → slipper å blokkere event loop
            tasks.append(
                asyncio.to_thread(
                    self.save_attachment,
                    content=content_bytes,
                    path=path,
                    bucket_name=bucket_name
                )
            )

        # Kjør alle parallelt
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"All {len(attachments)} attachments saved to Supabase Storage.")
    
    def read_attachment(self, path : str, bucket_name: str = "session_attachments") -> bytes:
        response = self.supabase.storage.from_(bucket_name)\
            .download(path)
        return response
