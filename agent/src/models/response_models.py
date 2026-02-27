from pydantic import BaseModel
from typing import Optional
from .api_request_models import AttachmentModel
from .project_models import FactSheet, Attachment, Email
from .api_request_models import StreamEvent


class SessionHistory(BaseModel):
    events: list[StreamEvent]
    attachments: list[AttachmentModel]
    project_id: str
    title: str
    llm_model: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectData(BaseModel):
    factsheet: FactSheet
    attachments: list[Attachment]
    emails: list[Email]


class ProjectSummary(BaseModel):
    project_id: str
    title: Optional[str] = None
    created_at: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    title: Optional[str] = None
    llm_model: Optional[str] = None
    updated_at: Optional[str] = None
