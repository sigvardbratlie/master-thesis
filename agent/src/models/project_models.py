from pydantic import BaseModel, Field, field_validator
from typing import Literal, TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from datetime import datetime,date
import uuid
from langgraph.graph.message import add_messages
from .api_request_models import FileType
import logging
logger = logging.getLogger(__name__)

# ===== CONTEXT MANAGER MODELS
PartyRole = Literal[
    # Sivile hovedparter
    "plaintiff",
    "defendant",
    "appellant",
    "respondent",

    # Straffesak
    "prosecutor",
    "defense_counsel",
    "injured_party",
    "injured_party_counsel",

    # Representanter
    "legal_rep_plaintiff",
    "legal_rep_defendant",
    "legal_rep_appellant",
    "legal_rep_respondent",
    "party_representative",   # prosessfullmektig som ikke er advokat
    "guardian",               # verge/fullmektig
    "estate_representative",  # bobestyrer/dødsbo

    # Rettsaktører
    "judge",
    "court_clerk",
    "witness",
    "expert",
    "translator",

    # Andre prosessroller
    "third_party",
    "intervener",
    "insurer",
    "employer",
    "employee",
    

    # Real estate
    "contractor",
    "subcontractor",
    "tenant",
    "landlord",
    "property_manager",

    "other"
]

entity_types = Literal["individual", "company", "government"]

significance_levels = Literal["high", "medium", "low"]

def shorten_element(elements : list,  
                    element_name : Literal["attachments", "emails","events", "parties", "claims", "damages", "deadlines"] , 
                    format_keys : list[str], 
                    significance: list[Literal["high", "medium", "low"]] = None,
                    include_reference_ids: bool = False) -> str:
        type_map = {
            "attachments": Attachment, 
            "emails": Email,
            "events" : Event,
            "parties" : Party,
            "claims" : Claim,
            "damages" : Damage,
            "deadlines" : Deadline
            }
        if not elements:
            return f"No {element_name.capitalize()}.\n\n"
        element_id_map = {
            "attachments": "file_id",
            "emails": "email_id",
            "events": "event_id",
            "parties": "party_id",
            "claims": "claim_id",
            "damages": "damage_id",
            "deadlines": "deadline_id"
        }
        element_id_key = element_id_map.get(element_name)
        presented_format_keys = ["id" if key == element_id_key else key for key in format_keys] + (["reference_id"] if include_reference_ids and element_name not in ["attachments", "emails", "parties"] else [])
        view = ""
        view += "**FORMAT: " + " | ".join(presented_format_keys) + "**\n"
        for item in elements:
            if not isinstance(item, type_map[element_name]):
                logger.warning(f'Item is of wrong type: {type(item)}. Expected type {type_map[element_name]. __name__}. Skipping item.')
                continue
            if significance and item.significance not in significance:
                continue
            row = " | ".join([str(getattr(item, key)) for key in format_keys])
            if include_reference_ids and element_name not in ["attachments", "emails", "parties"]:
                reference_id = getattr(item, "email_id", None) or getattr(item, "file_id", None)
                row += f" | {reference_id}" if reference_id else " | "
            view += f"\t* {row}\n"
        return f"{element_name.capitalize()}:\n" + view + "\n\n"

# === #Custom fields === 

class Claim(BaseModel):
    claim_id : str | None = None
    legal_basis: str = Field(description="Statutory basis (e.g., avtaleloven §36)")
    factual_basis: str = Field(description="Key facts supporting this claim")
    relief_sought: str = Field(description="What is being claimed (damages, injunction, etc)")
    strength_assessment: Literal["strong", "moderate", "weak"] = Field(
        description="Assessment of claim strength"
    )
    defense: str | None = Field(None, description="Defense strategy if defending")
    file_id: str | None = None  # For claims from attachments
    email_id: str | None = None  # For claims from emails
    party_role : PartyRole | None = None
    significance : significance_levels = Field(default="medium", description="Significance of the claim to the case")

class Claims(BaseModel):
    claims: list[Claim] = Field(description="Legal claims made by the parties, including legal and factual basis, relief sought, and strength assessment")

class Damage(BaseModel):
    damage_id: str | None = None
    category: Literal["direct_losses", "interest", "consequential", "punitive"]
    amount: int | float | None = Field(None, description="Monetary amount if amount is known and mentioned, else None")
    currency: str | None = Field(None, description="Currency of the amount, e.g., 'NOK', 'USD', etc.")
    basis: str
    supporting_evidence: list[str] = Field(description="File_IDs supporting the damage claim")
    file_id: str | None = None  # For damages from attachments
    email_id: str | None = None  # For damages from emails
    party_role: PartyRole | None = None
    significance : significance_levels = Field(default="medium", description="Significance of the damage claim to the case")
    
class Damages(BaseModel):
    damages: list[Damage] = Field(description="Information about damages claimed or incurred in the case, including type, amount if mentioned, evidentiary basis, and associated party roles")

def _coerce_partial_date(v):
    """Coerce YYYY-MM or YYYY to YYYY-MM-01 / YYYY-01-01. Returns None for non-date strings."""
    if isinstance(v, (date, datetime)):
        return v
    if isinstance(v, str):
        parts = v.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            v = f"{v}-01"
        elif len(parts) == 1 and parts[0].isdigit():
            v = f"{v}-01-01"
        else:
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                return None
    return v


class Deadline(BaseModel):
    deadline_id: str | None = None
    deadline_date: date | datetime | None

    @field_validator("deadline_date", mode="before")
    @classmethod
    def coerce_deadline_date(cls, v):
        return _coerce_partial_date(v)
    description: str
    file_id: str | None = Field(None, description="Related attachment reference")
    email_id: str | None = None  # For deadlines from emails
    party_role : PartyRole | None = None
    significance : significance_levels = Field(default="medium", description="Significance of the deadline to the case")

class Deadlines(BaseModel):
    deadlines: list[Deadline] = Field(description="Important deadlines mentioned in the case, e.g., contract milestones, court dates, statute of limitations, etc.")

# ====== BASIC FIELDS =====
class Contact(BaseModel):
    name: str = Field(description="Full name of contact person")
    title: str | None = None
    phone: str | None = None
    email: str | None = None

class Party(BaseModel):
    legal_name: str
    party_id : str | None = None
    role: PartyRole = Field(
        default="other",
        description="Functional role of the party. Use 'legal_rep_*' roles ONLY for qualified legal counsel (lawyers/attorneys). For professional service providers (architects, consultants, engineers, etc.) use 'contractor' or 'party_representative'. Assign based on the party's actual function, not assumed litigation framing.")
    entity_type: entity_types
    key_contact: Contact | None = Field(None, description="Primary contact person for this party")
    role_description: str | None = Field(None, description="Additional details about the party's role or involvement in the case")
    significance : significance_levels = Field(default="medium", description="Significance of the party to the case")


class Parties(BaseModel):
    parties: list[Party] = Field(description="List of parties involved in the case, i.e., plaintiff, defendant, witnesses, plaintiffs legal representatives, etc.")

class Event(BaseModel):
    event_id: str | None = None
    file_id: str | None = None  # For events from attachments
    email_id: str | None = None  # For events from emails
    event_name: str
    event_start_date: date | datetime
    event_end_date: date | datetime | None = None

    @field_validator("event_start_date", "event_end_date", mode="before")
    @classmethod
    def coerce_event_dates(cls, v):
        return _coerce_partial_date(v)
    description: str
    category: str = Field(description="Categorization of the event, e.g., 'court_filing', 'evidence_submission', 'contract_signing', 'communication', etc.")
    parties: list[str] | None = Field(None, description="Roles of parties involved in the event")
    significance: significance_levels = Field(default="medium", description="Significance of the event to the case")
    disputed: bool

class Events(BaseModel):
    events: list[Event]

class InitialInput(BaseModel):
    # Factual background
    parties: list[Party] | None = Field([], description="List of parties involved in the case.")
    background: str | None = Field("", description="Brief factual background of the case, including key events, timeline, and context")
    title : str | None = Field("", description="Title of the case or matter (MAX 10 words)")
    start_date: date | datetime | None = Field(None, description="Start date of the case or matter. Must be a valid date or datetime (e.g., '2023-05-01' or '2023-05-01T14:30:00')")

class BaseExtracted(BaseModel):
    """Common extraction fields for all document types and emails"""
    title : str = Field(description="Concise title of the content (MAX 10 words)")
    description: str = Field(description="Concise summary of the content")
    significance: significance_levels = Field(default="medium", description="Importance level")
    party_roles: list[str] | None = Field(None, description="Party roles mentioned")
    deadlines: list[Deadline] | None = Field(None, description="Relevant deadlines if any")
    damages: list[Damage] | None = Field(None, description="Damage information if applicable")
    claims: list[Claim] | None = Field(None, description="Claim information if applicable")

class AttachmentExtracted(BaseExtracted):
    """Document-specific extraction fields"""
    file_id: str | None = None
    key_provisions: list[str] | None = Field(None, description="Important clauses or sections (for agreements)")
    file_date: date | datetime | None = Field(None, description="Date of the document (when it was created/sent, not when it was received). Must be a valid date or datetime (e.g., '2023-05-01' or '2023-05-01T14:30:00')")

    @field_validator("file_date", mode="before")
    @classmethod
    def coerce_empty_date(cls, v):
        if v == "":
            return None
        return v
    category: Literal[
        "agreement", "correspondence", "meeting_minutes", "pleading", "evidence",
        "court_order", "invoice", "expert_report", "witness_statement", "internal_memo",
        "legal_opinion", "settlement_proposal", "power_of_attorney", "other"
    ] = Field(
        default="other",
        description="REQUIRED: Document category - select the most appropriate type. Choose 'agreement' for contracts, 'correspondence' for letters, 'pleading' for court submissions, 'evidence' for supporting documents, 'court_order' for rulings, 'expert_report' for expert analyses, etc. If unclear, use 'other'"
    )

class Attachment(AttachmentExtracted):
    file_id: str | None = None
    filename: str
    path: str 
    file_type: FileType #system generated
    body : str | None = None
    size: int #system generated
    #events: list[str] | None = Field(None, description="event IDs mentioned in the document")
    email_id: str | None = Field(None, description="If this attachment was extracted from an email, reference the email_id here")


class EmailExtracted(BaseExtracted):
    """Email-specific extraction fields - what LLM extracts from email content"""
    key_points: list[str] | None = Field(None, description="Important points, decisions, or action items from the email")
    # Legal metadata
    #privilege_status: Literal["attorney-client", "work_product", "none"] | None = Field(
    #     None, description="Privilege classification"
    # )
    email_id : str | None = None 

class Email(EmailExtracted):
    """Email model - Python-friendly names with RFC aliases"""
    # IDs
    #email_id: str | None = None
    project_id: str | None = None
    
    # Core RFC 5322 headers - lowercase Python names
    from_addr: str = Field(alias="from")  # ✅ Python-friendly
    to: list[str] = Field(default_factory=list)
    cc: list[str] | None = Field(default_factory=list)
    bcc: list[str] | None = Field(default_factory=list)
    subject: str
    date: datetime
    
    # Threading
    message_id: str = Field(alias="message-id")
    in_reply_to: str | None = Field(None, alias="in-reply-to")
    references: str | None = None
    thread_topic: str | None = Field(None, alias="thread-topic")
    thread_index: str | None = Field(None, alias="thread-index")
    thread_id: str | None = None
    
    # Content
    body: str
    html: str | None = None
    
    # Metadata
    headers: dict = Field(default_factory=dict)
    #attachments: list[str] = Field(default_factory=list)
    size: int | None = None
    path : str | None = None

    reference_paths: list[str] | None = Field(None, description="File paths of attachments referenced in the email thread, separated by newlines")
    
    class Config:
        populate_by_name = True  # Accept both 'from_addr' and 'from'

class Emails(BaseModel):
    emails: list[Email] = Field(description="List of emails in the project")
    
class FactSheet(InitialInput,
                #FactualFacts
                ):
    """Structured representation of case facts for legal analysis."""
    project_id: str | None = None
    events: list[Event] 
    claims: list[Claim] | None = None
    damages: list[Damage] | None = None
    deadlines: list[Deadline] | None = None

    def shorten_events(self, significance: list[Literal["high", "medium", "low"]] = None) -> str:
        shorten_keys = ["event_start_date", "event_name", "file_id", "description", "disputed"]
        return shorten_element(self.events,  
                               element_name="events", 
                               format_keys=shorten_keys, 
                               significance=significance)
        # return self.shorten_element(  
        #                        element_name="events", 
        #                        format_keys=shorten_keys, 
        #                        significance=significance)
        

    def shorten_parties(self, significance: list[Literal["high", "medium", "low"]] = None) -> str:
        shorten_keys = ["legal_name", "entity_type", "role", "role_description"]
        return shorten_element(self.parties, 
                                element_name="parties", 
                                format_keys=shorten_keys, 
                                significance=significance)
        # return self.shorten_element(
        #                         element_name="parties", 
        #                         format_keys=shorten_keys, 
        #                         significance=significance)
        

    def shorten_claims(self, significance : list[Literal["high", "medium", "low"]] = None) -> str:
        shorten_keys = ["relief_sought", "factual_basis", "legal_basis"]
        return shorten_element(self.claims, 
                                element_name="claims", 
                               format_keys=shorten_keys, significance=significance)
        # return self.shorten_element( 
        #                         element_name="claims", 
        #                        format_keys=shorten_keys, significance=significance)
        

    def shorten_damages(self, significance : list[Literal["high", "medium", "low"]] = None) -> str:
        shorten_keys = ["category", "amount", "currency", "basis",]
        return shorten_element(self.damages, 
                                element_name="damages", 
                                format_keys=shorten_keys, 
                                significance=significance)
        # return self.shorten_element(
        #                         element_name="damages", 
        #                         format_keys=shorten_keys, 
        #                         significance=significance)

    def shorten_deadlines(self, significance : list[Literal["high", "medium", "low"]] = None) -> str:
        shorten_keys = ["deadline_date", "description","file_id", "email_id"]
        return shorten_element(self.deadlines, 
                                element_name="deadlines", 
                                format_keys=shorten_keys, 
                                significance=significance)
        # return self.shorten_element(
        #                         element_name="deadlines", 
        #                         format_keys=shorten_keys, 
        #                         significance=significance)
    
    def shorten_factsheet(self, 
                          excluded_fields: list[Literal["events", "parties", "claims", "damages", "deadlines", "background"]] = None,
                          significance: list[Literal["high", "medium", "low"]] = None) -> str:
        view = f"Factsheet for project: {self.title} (ProjectId : {self.project_id}):\n\n"
        view += f"Background\n {self.background}\n\n" if self.background and (not excluded_fields or "background" not in excluded_fields) else ""
        view += self.shorten_parties(significance) if not excluded_fields or "parties" not in excluded_fields else ""
        view += self.shorten_events(significance) if not excluded_fields or "events" not in excluded_fields else ""
        view += self.shorten_claims(significance) if self.claims and (not excluded_fields or "claims" not in excluded_fields) else ""
        view += self.shorten_damages(significance) if self.damages and (not excluded_fields or "damages" not in excluded_fields) else ""
        view += self.shorten_deadlines(significance) if self.deadlines and (not excluded_fields or "deadlines" not in excluded_fields) else ""
        return view
    