import asyncio
import logging
import base64
import time

from google.cloud import storage

from models.api_request_models import *
from .storage_base import BaseStorageManager
from utils import AppConfig

logger = logging.getLogger(__name__)


class GCSManager(BaseStorageManager):
    def __init__(self, config: AppConfig):
        super().__init__(config)
        self.client = storage.Client()
        self.bucket = self.client.bucket(self.config.storage.gcs.bucket_name)
        self.prefix = "attachments/"

    def save_attachment(self,
                        content: bytes,
                        path: str,
                        metadata: dict = None) -> str | None:
        """Upload a single file to GCS with retry logic.

        Returns:
            The storage path if upload succeeded, None if all retries fail.
        """
        save_path = self.prefix + path
        last_error = None

        for attempt in range(self.config.storage.max_retries):
            try:
                blob = self.bucket.blob(save_path)
                if metadata:
                    blob.metadata = metadata
                blob.upload_from_string(content)
                logger.info(f"✅ Saved to GCS: {save_path}")
                return path

            except Exception as e:
                last_error = e
                error_msg = str(e)

                if "409" in error_msg or "already exists" in error_msg:
                    logger.info(f"✅ File already exists at {save_path} — treating as success")
                    return path

                if attempt < self.config.storage.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"⚠️ Retry {attempt + 1}/{self.config.storage.max_retries} for {save_path} "
                        f"after {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"❌ GCS upload attempt {attempt + 1}/{self.config.storage.max_retries} failed for {save_path} "
                        f"| filename: {metadata.get('filename') if metadata else 'Unknown'}: {e}"
                    )

        logger.error(
            f"❌ Upload failed after {self.config.storage.max_retries} attempts for {save_path} "
            f"| filename: {metadata.get('filename') if metadata else 'Unknown'}: {last_error}"
        )
        return None

    async def save_raw_documents(self, attachments: list[AttachmentModel]) -> bool:
        """Save attachments with controlled concurrency using semaphore."""
        semaphore = asyncio.Semaphore(self.config.storage.max_concurrent_uploads)
        results = {}

        async def upload_with_semaphore(att: AttachmentModel):
            async with semaphore:
                content_bytes = base64.b64decode(att.content)
                result = await asyncio.to_thread(
                    self.save_attachment,
                    content=content_bytes,
                    path=att.path,
                    metadata={"filename": att.filename, "file_type": att.file_type},
                )
                results[att.file_id] = result
                return result

        tasks = [upload_with_semaphore(att) for att in attachments]
        await asyncio.gather(*tasks, return_exceptions=False)

        successful = sum(1 for v in results.values() if v is not None)
        failed = len(results) - successful
        logger.info(f"💾 Upload complete: {successful}/{len(attachments)} succeeded, {failed} failed")
        return True

    def read_attachment(self, path: str) -> bytes | None:
        read_path = self.prefix + path
        try:
            blob = self.bucket.blob(read_path)
            content = blob.download_as_bytes()
            logger.info(f"✅ Read from GCS: {read_path}")
            return content
        except Exception as e:
            logger.error(f"❌ GCS read failed for {read_path}: {e}")
            return None

    def read_attachments(self, paths: list[str]) -> dict[str, bytes | None]:
        """Batch read by listing all blobs under the prefix, then downloading matches."""
        read_paths = {self.prefix + path: path for path in paths}
        results: dict[str, bytes | None] = {path: None for path in paths}

        blobs = self.bucket.list_blobs(prefix=self.prefix)
        for blob in blobs:
            if blob.name not in read_paths:
                continue
            original_path = read_paths[blob.name]
            try:
                results[original_path] = blob.download_as_bytes()
                logger.info(f"✅ Read from GCS: {blob.name}")
            except Exception as e:
                logger.error(f"❌ GCS read failed for {blob.name}: {e}")

        return results

    def delete_attachment(self, path: str) -> None:
        delete_path = self.prefix + path
        blob = self.bucket.blob(delete_path)
        blob.delete()
        logger.info(f"✅ Deleted from GCS: {delete_path}")
            
