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
        format_keys = ["file_id", "file_date", "title"] + (["description",] if not excluded_keys or "description" not in excluded_keys else [])
        # return self.shorten_attachment_type(
        #                         element_name="attachments",
        #                         format_keys=format_keys, 
        #                         significance=significance)
        return shorten_element(self.attachments, 
                                    element_name="attachments",
                                    format_keys=format_keys, 
                                    significance=significance)
        # return self.factsheet.shorten_element(
        #                 element_name="attachments",
        #                 format_keys=format_keys, 
        #                 significance=significance)
    
    def shorten_emails(self, excluded_keys: list[Literal["description"]] = None, 
                       significance: list[Literal["high", "medium", "low"]] = None) -> str:
        format_keys = ["email_id", "from_addr", "to", "subject", "date", "title"] + (["description"] if not excluded_keys or "description" not in excluded_keys else [])
        # return self.shorten_attachment_type(
        #                     element_name="emails", 
        #                     format_keys=format_keys, 
        #                     significance=significance)
        return shorten_element(self.emails, 
                            element_name="emails", 
                            format_keys=format_keys, 
                            significance=significance)
        # return self.factsheet.shorten_element(
        #                     element_name="emails", 
        #                     format_keys=format_keys, 
        #                     significance=significance)
    
    def shorten_project(self,inclued_fields: list[Literal["events", "parties", "claims", "damages","title", "background", "emails", "attachments"]] = None,
                            excluded_fields: list[Literal["events", "parties", "claims", "damages","title", "background", "emails", "attachments"]] = None,
                            excluded_keys: list[Literal["description"]] = ["description"],
                          significance: list[Literal["high", "medium", "low"]] = None) -> str:
        if inclued_fields and excluded_fields:
            logger.warning("Both inclued_fields and excluded_fields are provided. inclued_fields will take precedence and excluded_fields will be ignored.")
            inclued_fields = None
        if inclued_fields:
            excluded_fields = [field for field in ["events", "parties", "claims", "damages","title", "background", "emails", "attachments"] if field not in inclued_fields]
        
        view = ""
        view += self.shorten_factsheet(excluded_fields=excluded_fields, significance=significance)
        view += self.shorten_attachments(excluded_keys=excluded_keys, significance=significance) if not excluded_fields or "attachments" not in excluded_fields else ""
        view += self.shorten_emails(excluded_keys=excluded_keys, significance=significance) if not excluded_fields or "emails" not in excluded_fields else ""
        return view
    
    
    # def shorten_attachment_type(self, element_name : Literal["attachments", "emails",] , format_keys : list[str], significance: list[Literal["high", "medium", "low"]] = None) -> str:
    #     type_map = {
    #         "attachments": Attachment, 
    #         "emails": Email,
    #         }
    #     elements = getattr(self, element_name, [])
    #     if not elements:
    #         return f"No {element_name.capitalize()}.\n\n"
    #     user_id = None
    #     if "path" in format_keys and hasattr(elements[0], "path"):
    #         user_id = elements[0].path.split("/")[0] if len(elements[0].path.split("/")) == 3 else None
    #     else:
    #         logger.warning(f'Element type {element_name} does not have a "path" attribute. User ID will not be extracted for shortening.')
    #     view = ""
    #     if user_id:
    #         view += f"**user_id: {user_id}**\n"
    #         view += "**FORMAT: <session_id>/<file_id> | " + " | ".join(k for k in format_keys if k != "path") + "**\n"
    #     else:
    #         view += "**FORMAT: " + " | ".join(format_keys) + "**\n"
    #     for item in elements:
    #         if not isinstance(item, type_map[element_name]):
    #             logger.warning(f'Item is of wrong type: {type(item)}. Expected type {type_map[element_name]. __name__}. Skipping item.')
    #             continue
    #         if significance and item.significance not in significance:
    #             continue

    #         values = []
    #         for key in format_keys:
    #             value = getattr(item, key, "")
    #             if key == "path" and user_id and isinstance(value, str):
    #                 value = value.removeprefix(user_id + "/")
    #             values.append(str(value))
    #         view += "\t* " + " | ".join(values) + "\n"
    #     return f"{element_name.capitalize()}:\n" + view + "\n\n"

class ProjectSummary(BaseModel):
    project_id: str
    title: str | None = None
    created_at: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    title: str | None = None
    llm_model: str | None = None
    updated_at: str | None = None
