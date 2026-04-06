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
    path: str


@router.post("/signed-url")
async def get_signed_url(
    req: SignedUrlRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Generer en signed URL for en GCS-fil.
    Speil av database_service.py read_attachment() — men returnerer URL
    i stedet for bytes, slik at browser kan hente direkte fra GCS.
    """
    try:
        client = _get_storage_client()
        blob   = client.bucket(GCS_BUCKET).blob(GCS_PREFIX + req.path)
        url    = blob.generate_signed_url(
            expiration=SIGNED_URL_TTL,
            method="GET",
            version="v4",
        )
        logger.info(f"✅ Signed URL generert for {req.path} (user: {user_id})")
        return {"url": url}
    except Exception as e:
        logger.exception(f"❌ Signed URL feilet for {req.path}")
        raise HTTPException(status_code=500, detail=str(e))
