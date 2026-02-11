from pydantic import BaseModel, Field
from typing import Optional, Literal
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from datetime import datetime,date
import uuid
from langgraph.graph.message import add_messages


FileTypes = Literal["application/pdf", "text/plain", "application/msword","message/rfc822","text/csv",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", #"application/",
                    ]
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

# === #Custom fields === 
class GoverningLaw(BaseModel):
    primary_jurisdiction: str = Field(default = "norwegian_law" , description="Which law governs (e.g., Norwegian law)")
    key_areas: list[str] = Field(default_factory=list, description="Relevant legal areas (contract law, tort, etc)")
    international_elements: Optional[str] = Field(
        None, description="Cross-border or conflicts of law issues"
    )
    procedural_law: Literal[
        "tvisteloven", "straffeprosessloven", "arbeidstvistloven", "voldgiftsloven",
        "forvaltningsloven", "domstolloven"
    ] = Field(default="tvisteloven",description="Applicable procedural law, if relevant")

class FactualFacts(BaseModel):
    disputed_facts: list[str]
    undisputed_facts: list[str]

class Claim(BaseModel):
    claim_id : Optional[str] = None
    legal_basis: str = Field(description="Statutory basis (e.g., avtaleloven §36)")
    factual_basis: str = Field(description="Key facts supporting this claim")
    relief_sought: str = Field(description="What is being claimed (damages, injunction, etc)")
    strength_assessment: Literal["strong", "moderate", "weak"] = Field(
        description="Assessment of claim strength"
    )
    defense: Optional[str] = Field(None, description="Defense strategy if defending")
    file_id: Optional[str] = None  # For claims from attachments
    email_id: Optional[str] = None  # For claims from emails
    party_role : Optional[PartyRole] = None

class Claims(BaseModel):
    claims: list[Claim] = Field(description="Legal claims made by the parties, including legal and factual basis, relief sought, and strength assessment")

class Damage(BaseModel):
    damage_id: Optional[str] = None
    category: Literal["direct_losses", "interest", "consequential", "punitive"]
    amount: Optional[int | float] = Field(None, description="Monetary amount if amount is known and mentioned, else None")
    basis: str
    supporting_evidence: list[str] = Field(description="File_IDs supporting the damage claim")
    file_id: Optional[str] = None  # For damages from attachments
    email_id: Optional[str] = None  # For damages from emails
    party_role: Optional[PartyRole] = None

class Damages(BaseModel):
    damages: list[Damage] = Field(description="Information about damages claimed or incurred in the case, including type, amount if mentioned, evidentiary basis, and associated party roles")

class Deadline(BaseModel):
    deadline_id: Optional[str] = None
    deadline_date: date |datetime
    description: str
    file_id: Optional[str] = Field(None, description="Related attachment reference")
    email_id: Optional[str] = None  # For deadlines from emails
    party_role : Optional[PartyRole] = None

class Deadlines(BaseModel):
    deadlines: list[Deadline] = Field(description="Important deadlines mentioned in the case, e.g., contract milestones, court dates, statute of limitations, etc.")

# ====== BASIC FIELDS =====
class Contact(BaseModel):
    name: str = Field(description="Full name of contact person")
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

class Party(BaseModel):
    legal_name: str
    party_id : Optional[str] = None
    role: PartyRole = Field(
        default="other",
        description="Role of the party in the case, e.g., plaintiff, defendant, witness, legal representative, etc.")
    entity_type: entity_types
    key_contact: Optional[Contact] = Field(None, description="Primary contact person for this party")
    #corporation : bool = Field(..., description="Is this party a company/organization (True) or an individual (False)")
    # legal_representation: Optional[str] = Field(
    #     None, description="Law firm representing this party"
    # )

class Parties(BaseModel):
    parties: list[Party] = Field(description="List of parties involved in the case, i.e., plaintiff, defendant, witnesses, plaintiffs legal representatives, etc.")

class Event(BaseModel):
    event_id: Optional[str] = None
    file_id: Optional[str] = None  # For events from attachments
    email_id: Optional[str] = None  # For events from emails
    event_name: str
    event_start_date: date | datetime
    event_end_date: Optional[date | datetime] = None
    description: str
    category: str = Field(description="Categorization of the event, e.g., 'court_filing', 'evidence_submission', 'contract_signing', 'communication', etc.")
    parties: list[PartyRole] = Field(description="Roles of parties involved in the event")
    significance: significance_levels
    disputed: bool

class Events(BaseModel):
    events: list[Event]

class InitialInput(BaseModel):
    # Factual background
    parties: Optional[list[Party]] = Field([], description="List of parties involved in the case, i.e., plaintiff, defendant, witnesses, plaintiffs legal representatives, etc.")
    background: Optional[str] = Field("", description="Brief factual background of the case, including key events, timeline, and context")
    title : Optional[str] = Field("", description="Title of the case or matter")

class BaseExtracted(BaseModel):
    """Common extraction fields for all document types and emails"""
    description: str = Field(description="Concise summary of the content")
    significance: significance_levels = Field(default="medium", description="Importance level")
    party_roles: Optional[list[PartyRole]] = Field(None, description="Party roles mentioned")
    deadlines: Optional[list[Deadline]] = Field(None, description="Relevant deadlines if any")
    damages: Optional[list[Damage]] = Field(None, description="Damage information if applicable")
    claims: Optional[list[Claim]] = Field(None, description="Claim information if applicable")

class AttachmentExtracted(BaseExtracted):
    """Document-specific extraction fields"""    
    key_provisions: Optional[list[str]] = Field(None, description="Important clauses or sections (for agreements)")
    file_date: Optional[date] = Field(None, description="Date of the document (when it was created/sent, not when it was received)")
    category: Literal[
        "agreement", "correspondence", "meeting_minutes", "pleading", "evidence",
        "court_order", "invoice", "expert_report", "witness_statement", "internal_memo",
        "legal_opinion", "settlement_proposal", "power_of_attorney", "other"
    ] = Field(
        default="other",
        description="REQUIRED: Document category - select the most appropriate type. Choose 'agreement' for contracts, 'correspondence' for letters, 'pleading' for court submissions, 'evidence' for supporting documents, 'court_order' for rulings, 'expert_report' for expert analyses, etc. If unclear, use 'other'"
    )

class Attachment(AttachmentExtracted):
    file_id: Optional[str] = None
    filename: str
    path: str 
    file_type: FileTypes #system generated
    body : Optional[str] = None
    size: int #system generated
    events: Optional[list[str]] = Field(None, description="event IDs mentioned in the document")
    email_id: Optional[str] = Field(None, description="If this attachment was extracted from an email, reference the email_id here")


class FactSheet(InitialInput,FactualFacts):
    """Structured representation of case facts for legal analysis."""
    project_id: Optional[str] = None
    events: list[Event] #prior variable name: timeline 
    governing_law: GoverningLaw 
    claims: Optional[list[Claim]] = None
    damages: Optional[list[Damage]] = None
    deadlines: Optional[list[Deadline]] = None


class RelevanceCheck(BaseModel):
    is_relevant: bool
    reasoning: str

class EmailExtracted(BaseExtracted):
    """Email-specific extraction fields - what LLM extracts from email content"""
    key_points: Optional[list[str]] = Field(None, description="Important points, decisions, or action items from the email")
    # Legal metadata
    #privilege_status: Optional[Literal["attorney-client", "work_product", "none"]] = Field(
    #     None, description="Privilege classification"
    # )
    email_id : Optional[str] = None 

class Email(EmailExtracted):
    """Email model - Python-friendly names with RFC aliases"""
    
    # IDs
    #email_id: Optional[str] = None
    project_id: Optional[str] = None
    
    # Core RFC 5322 headers - lowercase Python names
    from_addr: str = Field(alias="from")  # ✅ Python-friendly
    to: list[str] = Field(default_factory=list)
    cc: Optional[list[str]] = Field(default_factory=list)
    bcc: Optional[list[str]] = Field(default_factory=list)
    subject: str
    date: datetime
    
    # Threading
    message_id: str = Field(alias="message-id")
    in_reply_to: Optional[str] = Field(None, alias="in-reply-to")
    references: Optional[str] = None
    thread_topic: Optional[str] = Field(None, alias="thread-topic")
    thread_index: Optional[str] = Field(None, alias="thread-index")
    thread_id: Optional[str] = None
    
    # Content
    body: str
    html: Optional[str] = None
    
    # Metadata
    headers: dict = Field(default_factory=dict)
    #attachments: list[str] = Field(default_factory=list)
    size: Optional[int] = None
    
    class Config:
        populate_by_name = True  # Accept both 'from_addr' and 'from'

class Emails(BaseModel):
    emails: list[Email] = Field(description="List of emails in the project")
    
    