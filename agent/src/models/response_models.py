from pydantic import BaseModel
from .api_request_models import AttachmentModel
from .project_models import FactSheet, Attachment, Email
from .api_request_models import StreamEvent
from typing import Literal


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

    def shorten_attachments(self, excluded_fields: list[Literal["description"]] = None, significance: list[Literal["high", "medium", "low"]] = None) -> str:
        view = ""
        
        if not self.attachments:
            return "No attachments.\n\n"
        view += "Attachments:\n"
        view += "\t* Format: path | filename | file_date" + (f" | description" if not excluded_fields or "description" not in excluded_fields else "") + "\n"
        for att in self.attachments:
            if significance and att.significance not in significance:
                continue
            view += f"\t* {att.path} | {att.filename} | {att.file_date}" + (f" | {att.description}" if not excluded_fields or "description" not in excluded_fields else "") + "\n"
        return view + "\n\n"
    
    def shorten_emails(self, excluded_fields: list[Literal["description"]] = None, significance: list[Literal["high", "medium", "low"]] = None) -> str:
        view = ""
        if not self.emails:
            return "No emails.\n\n"
        view += "Emails:\n"
        view += "\t* Format: path | from | to | subject | date" + (f" | description" if not excluded_fields or "description" not in excluded_fields else "") + "\n"
        for eml in self.emails:
            if significance and eml.significance not in significance:
                continue
            view += f"\t*{eml.path} | From: {eml.from_addr} | To: {', '.join(eml.to)} | Subject: {eml.subject} | Date: {eml.date}" + (f" | {eml.description}" if not excluded_fields or "description" not in excluded_fields else "") + "\n"
        return view + "\n\n"


class ProjectSummary(BaseModel):
    project_id: str
    title: str | None = None
    created_at: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    title: str | None = None
    llm_model: str | None = None
    updated_at: str | None = None
