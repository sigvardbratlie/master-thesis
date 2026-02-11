import asyncio
import os
import logging
import base64
import tempfile
import time
from typing import Optional

from google.cloud import storage

from models.api_request_models import *
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GCSManager:

    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "attachments")
        self.bucket = self.client.bucket(self.bucket_name)
    
    async def save_attachment(self,content : bytes | str, path : str):
        try:
            blob = self.bucket.blob(path)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.upload_from_string, content)
            logger.info(f"Attachment saved to GCS at {path}")
        except Exception as e:
            logger.error(f"Error saving attachment to GCS: {e}")

    async def save_raw_documents(self, attachments: list[AttachmentModel], bucket_name: str = "attachments"):
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
    def __init__(self, max_concurrent_uploads: int = 1):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)
        self.max_concurrent_uploads = max_concurrent_uploads

    def save_attachment(self, content: bytes | str, path : str, bucket_name: str = "attachments", max_retries: int = 3) -> Optional[str]:
        """Save attachment with retry logic for transient errors"""
        if isinstance(content, str):
            content = content.encode('utf-8')
        
        tmp_path = None
        last_error = None
        
        for attempt in range(max_retries):
            try:
                # Opprett midlertidig fil med unikt navn
                with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                
                # Last opp fra midlertidig fil
                with open(tmp_path, 'rb') as f:
                    self.supabase.storage.from_(bucket_name).upload(
                        path=path,
                        file=f,
                        file_options={"content-type": "application/octet-stream"}
                    )
                logger.info(f"Attachment saved to Supabase Storage at {path}")
                return path
            
            except Exception as e:
                last_error = e
                error_msg = str(e)
                
                # Check if file already exists (409 Duplicate)
                if "409" in error_msg or "Duplicate" in error_msg or "already exists" in error_msg:
                    logger.info(f"File already exists at {path}, treating as success")
                    return path
                
                # Retry on transient errors
                if "Resource temporarily unavailable" in error_msg or "[Errno 35]" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(f"Retry {attempt + 1}/{max_retries} for {path} after {wait_time}s (error: {e})")
                        time.sleep(wait_time)
                        continue
                
                logger.error(f"Error saving attachment to Supabase Storage (attempt {attempt + 1}/{max_retries}): {e}")
                break
            
            finally:
                # Slett midlertidig fil
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
        
        # If all retries failed
        logger.error(f"Failed to upload {path} after {max_retries} attempts: {last_error}")
        return None
            

    async def save_raw_documents(self, attachments: list[AttachmentModel], bucket_name: str = "attachments") -> dict[str, Optional[str]]:
        """Save attachments with controlled concurrency using semaphore"""
        semaphore = asyncio.Semaphore(self.max_concurrent_uploads)
        results = {}

        async def upload_with_semaphore(att: AttachmentModel):
            """Upload single attachment with semaphore control"""
            async with semaphore:
                path = att.path
                if att.file_type == "application/pdf":
                    content_bytes = base64.b64decode(att.content)
                else:
                    content_bytes = att.content

                # Kjør blocking I/O i thread → slipper å blokkere event loop
                result = await asyncio.to_thread(
                    self.save_attachment,
                    content=content_bytes,
                    path=path,
                    bucket_name=bucket_name
                )
                results[att.file_id] = result
                return result

        # Kjør alle med begrenset parallellitet
        tasks = [upload_with_semaphore(att) for att in attachments]
        await asyncio.gather(*tasks, return_exceptions=False)
        
        # Log summary
        successful = sum(1 for v in results.values() if v is not None)
        failed = len(results) - successful
        logger.info(f"Upload complete: {successful} succeeded, {failed} failed out of {len(attachments)} total")
        
        return results
    
    def read_attachment(self, path : str, bucket_name: str = "attachments") -> bytes:
        response = self.supabase.storage.from_(bucket_name)\
            .download(path)
        return response
