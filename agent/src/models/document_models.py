from pydantic import BaseModel
from typing import Optional, Literal
from .api_request_models import AttachmentModel
from datetime import datetime

class WriteEmail(BaseModel):
    from_addr: str
    to: list[str]
    cc: Optional[list[str]] = None
    bcc: Optional[list[str]] = None
    subject: str
    body: str
    attachments: Optional[list[AttachmentModel]] = None

class WriteDocx(BaseModel):
    file_name: str
    heading : Optional[str] = None
    paragraphs: list[str]
    