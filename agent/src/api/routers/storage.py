from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from google.cloud import storage as gcs
from google.oauth2 import service_account
import datetime
import os
import logging
from api.dependencies import get_current_user

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
