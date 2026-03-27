import asyncio
import os
import logging
import base64
import tempfile
import time

from google.cloud import storage

from models.api_request_models import *
from supabase import create_client
from .storage_base import BaseStorageManager
from utils import AppConfig

logger = logging.getLogger(__name__)

class SupabaseStorageManager(BaseStorageManager):
    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)
        self.bucket = self.supabase.storage.from_(self.config.storage.supabase.bucket_name)
        self.config = config

    def save_attachment(self, 
                        content: bytes, 
                        path : str, 
                        metadata : dict = None) -> str | None:
        """Save attachment with retry logic for transient errors
        
        Args:
            content: File content as bytes
            path : Storage path for the attachment, e.g., 'user_id/session_id/file_id.ext'. Should also end with extension
            bucket_name: Name of the Supabase Storage bucket
            max_retries: Maximum number of retries for transient errors

        Returns:
            The storage path if upload is successful or file already exists, None if all retries fail
        """
        
        tmp_path = None
        last_error = None
        
        for attempt in range(self.config.storage.max_retries):
            try:
                # Opprett midlertidig fil med unikt navn
                with tempfile.NamedTemporaryFile(delete=False, mode='wb') as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                
                # Last opp fra midlertidig fil
                with open(tmp_path, 'rb') as f:
                    self.bucket.upload(
                        path=path,
                        file=f,
                        file_options={"content-type": "application/octet-stream"}
                    )
                logger.info(f"✅ Saved to Supabase Storage: {path}")
                return path
            
            except Exception as e:
                last_error = e
                error_msg = str(e)
                
                # Check if file already exists (409 Duplicate)
                if "409" in error_msg or "Duplicate" in error_msg or "already exists" in error_msg:
                    logger.info(f"✅ File already exists at {path} — treating as success")
                    return path
                
                # Retry on transient errors
                if "Resource temporarily unavailable" in error_msg or "[Errno 35]" in error_msg:
                    if attempt < self.config.storage.max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(f"⚠️  Retry {attempt + 1}/{self.config.storage.max_retries} for {path} after {wait_time}s: {e}")
                        time.sleep(wait_time)
                        continue
                
                logger.error(f"❌ Supabase Storage upload attempt {attempt + 1}/{self.config.storage.max_retries} failed for path {path} | filename: {metadata.get('filename') if metadata else 'Unknown'}: {e}")
                break
            
            finally:
                # Slett midlertidig fil
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
        
        # If all retries failed
        logger.error(f"❌ Upload failed after {self.config.storage.max_retries} attempts for path {path} | filename: {metadata.get('filename') if metadata else 'Unknown'}: {last_error}")
        return None
            
    async def save_raw_documents(self, 
                                 attachments: list[AttachmentModel], 
                                 ) -> bool:
        """Save attachments with controlled concurrency using semaphore"""
        semaphore = asyncio.Semaphore(self.config.storage.max_concurrent_uploads)
        results = {}

        async def upload_with_semaphore(att: AttachmentModel):
            """Upload single attachment with semaphore control"""
            async with semaphore:
                path = att.path
                content_bytes = base64.b64decode(att.content)

                result = await asyncio.to_thread(
                    self.save_attachment,
                    content=content_bytes,
                    path=path,
                    metadata = {
                                "filename": att.filename,
                                "file_type": att.file_type}
                )
                results[att.file_id] = result
                return result

        # Kjør alle med begrenset parallellitet
        tasks = [upload_with_semaphore(att) for att in attachments]
        await asyncio.gather(*tasks, return_exceptions=False)
        
        # Log summary
        successful = sum(1 for v in results.values() if v is not None)
        failed = len(results) - successful
        logger.info(f"💾 Upload complete: {successful}/{len(attachments)} succeeded, {failed} failed")
        
        return True
    
    def read_attachment(self, path : str) -> bytes:
        response = self.bucket.download(path)
        return response
    
    def read_attachments(self, paths: list[str]) -> dict[str, bytes | None]:
        results = {}
        for path in paths:
            try:
                content = self.read_attachment(path)
                results[path] = content
            except Exception as e:
                logger.error(f"❌ Failed to read {path} from Supabase Storage: {e}")
                results[path] = None
        return results
    
    def delete_attachment(self, path : str) -> None:
        self.bucket.remove([path])
