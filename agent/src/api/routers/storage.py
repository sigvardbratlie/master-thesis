from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from google.cloud import storage as gcs
from google.oauth2 import service_account
import datetime
import asyncio
import os
import logging
from api.dependencies import get_current_user, get_gcs, get_conversation_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])

GCS_BUCKET     = os.getenv("GCS_BUCKET_NAME", "master-thesis-prod")
GCS_KEY_FILE   = os.getenv("GCS_KEY_FILE", "gcloud-keys.json")
GCS_PREFIX     = "attachments/"
SIGNED_URL_TTL = datetime.timedelta(minutes=60)


def _get_storage_client():
    creds = service_account.Credentials.from_service_account_file(
        GCS_KEY_FILE,
        scopes=["https://www.googleapis.com/auth/devstorage.read_only"],
    )
    return gcs.Client(credentials=creds)


class SignedUrlRequest(BaseModel):
    path:         str
    content_type: str = "application/pdf"

class DeleteFilesRequest(BaseModel):
    file_ids: list[str]


@router.get("/file")
async def stream_file(
    path:         str,
    content_type: str = "application/pdf",
    user_id:      str = Depends(get_current_user),
):
    """
    Stream en GCS-fil direkte gjennom backend med korrekte headers.
    Unngår alle cross-origin / Content-Type-problemer med signed URLs.
    """
    from fastapi.responses import StreamingResponse
    import io
    try:
        client  = _get_storage_client()
        blob    = client.bucket(GCS_BUCKET).blob(GCS_PREFIX + path)
        content = blob.download_as_bytes()
        logger.info(f"✅ Streamer fil {path} ({len(content)} bytes) til user {user_id}")
        return StreamingResponse(
            io.BytesIO(content),
            media_type=content_type,
            headers={"Content-Disposition": "inline"},
        )
    except Exception as e:
        logger.exception(f"❌ Stream feilet for {path}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-files")
async def delete_files_endpoint(
    body: DeleteFilesRequest,
    gcs_manager = Depends(get_gcs),
    conversation_manager = Depends(get_conversation_manager),
    user_id: str = Depends(get_current_user),
):
    """Delete GCS files by file_ids. Resolves paths via Supabase before deleting."""
    if not body.file_ids:
        return {"success": True, "deleted": 0, "failed": 0}
    try:
        paths = conversation_manager.get_paths(body.file_ids)
        deleted, failed = 0, 0
        for path in paths:
            try:
                await asyncio.to_thread(gcs_manager.delete_attachment, path)
                deleted += 1
            except Exception:
                logger.exception(f"❌ GCS delete failed for path: {path}")
                failed += 1
        logger.info(f"🗑️  GCS cleanup: {deleted} deleted, {failed} failed for {len(body.file_ids)} file_ids")
        return {"success": True, "deleted": deleted, "failed": failed}
    except Exception as e:
        logger.exception(f"❌ Error in /storage/delete-files")
        raise HTTPException(status_code=500, detail=str(e))
