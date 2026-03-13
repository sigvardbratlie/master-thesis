from pydantic import BaseModel
from .api_request_models import AttachmentModel
from .project_models import FactSheet, Attachment, Email, shorten_element
from .api_request_models import StreamEvent
from typing import Literal
import logging
logger = logging.getLogger(__name__)

class SessionHistory(BaseModel):
    events: list[StreamEvent]
    attachments: list[AttachmentModel]
    project_id: str
    title: str
    llm_model: str | None = None
    updated_at: str | None = None


class ProjectData(BaseModel):
    factsheet: FactSheet
    attachments: list[Attachment]
    emails: list[Email]

    def shorten_factsheet(self, 
                          excluded_fields: list[Literal["events", "parties", "claims", "damages","title", "background"]] = None,
                          significance: list[Literal["high", "medium", "low"]] = None) -> str:
        return self.factsheet.shorten_factsheet(excluded_fields=excluded_fields, significance=significance)

    def shorten_attachments(self, excluded_keys: list[Literal["description", ]] = None, significance: list[Literal["high", "medium", "low"]] = None) -> str:
        format_keys = ["path", "file_date","title"] + (["description",] if not excluded_keys or "description" not in excluded_keys else [])
        return shorten_element(self.attachments, 
                                element_name="attachments", 
                                format_key=format_keys, 
                                significance=significance)
    
    def shorten_emails(self, excluded_keys: list[Literal["description"]] = None, significance: list[Literal["high", "medium", "low"]] = None) -> str:
        format_keys = ["path", "from_addr", "to", "subject", "date", "title"] + (["description"] if not excluded_keys or "description" not in excluded_keys else [])
        return shorten_element(self.emails, 
                            element_name="emails", 
                            format_key=format_keys, 
                            significance=significance)
    
    def shorten_project(self,
                            excluded_fields: list[Literal["events", "parties", "claims", "damages","title", "background", "emails", "attachments"]] = None,
                            excluded_keys: list[Literal["description"]] = None,
                          significance: list[Literal["high", "medium", "low"]] = None) -> str:
        view = ""
        view += self.shorten_factsheet(excluded_fields=excluded_fields, significance=significance)
        view += self.shorten_attachments(excluded_keys=excluded_keys, significance=significance) if not excluded_fields or "attachments" not in excluded_fields else ""
        view += self.shorten_emails(excluded_keys=excluded_keys, significance=significance) if not excluded_fields or "emails" not in excluded_fields else ""
        return view

class ProjectSummary(BaseModel):
    project_id: str
    title: str | None = None
    created_at: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    title: str | None = None
    llm_model: str | None = None
    updated_at: str | None = None
