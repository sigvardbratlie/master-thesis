from pydantic import BaseModel
from typing import Literal
from .api_request_models import AttachmentModel
from datetime import datetime

class WriteEmail(BaseModel):
    from_addr: str
    to: list[str]
    cc: list[str] | None = None
    bcc: list[str] | None = None
    subject: str
    body: str
    attachments: list[AttachmentModel] | None = None

class WriteDocx(BaseModel):
    file_name: str
    heading : str | None = None
    paragraphs: list[str]
    