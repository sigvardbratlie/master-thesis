from pydantic import BaseModel, Field
from typing import Optional, Literal
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from datetime import datetime,date
import uuid
from langgraph.graph.message import add_messages



# ===== CONTEXT MANAGER MODELS
party_roles = ["plaintiff", "defendant", "claimant", "respondent","witness", "expert","third_party","other"]
entity_types = ["individual", "company", "government"]
event_categories = [
    "contract_signed", "breach_occurred", "notice_sent", "payment_due",
    "payment_made", "termination", "meeting", "court_filing", "court_hearing",
    "settlement_offer", "deadline", "other", 
]
significance_levels = ["high", "medium", "low"]

# === #Custom fields === 
class GoverningLaw(BaseModel):
    primary_jurisdiction: str = Field(description="Which law governs (e.g., Norwegian law)")
    key_areas: list[str] = Field(description="Relevant legal areas (contract law, tort, etc)")
    international_elements: Optional[str] = Field(
        None, description="Cross-border or conflicts of law issues"
    )
    procedural_law: Literal[
        "tvisteloven", "straffeprosessloven", "arbeidstvistloven", "voldgiftsloven",
        "forvaltningsloven", "domstolloven"
    ] 

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
    file_id: Optional[str] = None
    party_role : Optional[Literal["plaintiff", "defendant", "claimant", "respondent","witness", "expert","third_party","other"]] = None

class Claims(BaseModel):
    claims: list[Claim]

class Damage(BaseModel):
    damage_id: Optional[str] = None
    category: Literal["direct_losses", "interest", "consequential", "punitive"]
    amount: Optional[int | float] = Field(None, description="Monetary amount if amount is known and mentioned, else None")
    basis: str
    supporting_evidence: list[str] = Field(description="File_IDs supporting the damage claim")
    file_id: Optional[str] = None
    party_role: Optional[Literal["plaintiff", "defendant", "claimant", "respondent","witness", "expert","third_party","other"]] = None

class Damages(BaseModel):
    damages: list[Damage]

class Deadline(BaseModel):
    deadline_id: Optional[str] = None
    deadline_date: date |datetime
    description: str
    file_id: Optional[str] = Field(None, description="Related attachment reference")
    party_role : Optional[Literal["plaintiff", "defendant", "claimant", "respondent","witness", "expert","third_party","other"]] = None

class Deadlines(BaseModel):
    deadlines: list[Deadline]

# ====== BASIC FIELDS =====
class Contact(BaseModel):
    name: str = Field(description="Full name of contact person")
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

class Party(BaseModel):
    legal_name: str
    party_id : Optional[str] = None
    role: Literal["plaintiff", "defendant", "claimant", "respondent","witness", "expert","third_party","other"]
    entity_type: Literal["individual", "company", "government"]
    key_contact: Optional[Contact] = None
    legal_representation: Optional[str] = Field(
        None, description="Law firm representing this party"
    )

class Parties(BaseModel):
    parties: list[Party]

class Event(BaseModel):
    event_id: Optional[str] = None
    file_id: Optional[str] = None
    event_name: str
    event_date: date | datetime
    description: str
    category: Literal[
        "contract_signed", "breach_occurred", "notice_sent", "payment_due",
        "payment_made", "termination", "meeting", "court_filing", "court_hearing",
        "settlement_offer", "deadline", "other", 
    ]
    parties: list[Literal["plaintiff", "defendant", "claimant", "respondent","witness", "expert","third_party","other"]] = Field(description="Roles of parties involved in the event")
    significance: Literal["high", "medium", "low"]
    disputed: bool

class Events(BaseModel):
    events: list[Event]

class InitialInput(BaseModel):
    # Factual background
    parties: list[Party]
    background: str
    title : str = Field(description="Title of the case or matter")

class AttachmentExtracted(BaseModel):    
    description: str  = Field(description="Concise summary of the document content")
    key_provisions: Optional[list[str]] = Field(None, description="Important clauses or sections (for agreements)")
    #events: Optional[list[Event]] = Field(None, description="Key events mentioned in the document")
    party_ids: Optional[list] = Field(None, description="Party_IDs mentioned in the document")
    file_date : Optional[date] = None
    category: Literal[
        "agreement", "correspondence", "meeting_minutes", "pleading", "evidence",
        "court_order", "invoice", "expert_report", "witness_statement", "internal_memo",
        "legal_opinion", "settlement_proposal", "power_of_attorney", "other"
    ]
    deadlines: Optional[list[Deadline]] = Field(None, description="Relevant deadline if the document sets one")
    damages: Optional[list[Damage]] = Field(None, description="Damage information if applicable")
    claims: Optional[list[Claim]] = Field(None, description="Claim information if applicable")
    significance: Literal["high", "medium", "low"]

class Attachment(AttachmentExtracted):
    file_id: Optional[str] = None
    filename: str
    path: str 
    file_type: Literal["application/pdf", "text/plain", "application/msword",] #system generated
    size: int #system generated
    events: Optional[list[str]] = Field(None, description="event IDs mentioned in the document")


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



#=================================
# ===== API REQUEST MODELS =======
#=================================

class AttachmentModel(BaseModel):
    """Attachment sent to backend API"""
    filename: str
    file_id: str
    content: Optional[str] = None  # Base64 for PDF, text for others
    path : str
    file_type: str
    size: int
    query_id: str
    event_id: Optional[str] = None


class AskAgentRequest(BaseModel):
    """POST /ask-agent request"""
    question: str
    attachments: Optional[list[AttachmentModel]] = None
    session_id: str
    llm_model : str
    query_id: str
    project_id: Optional[str] = None


class StreamlitUserInfo(BaseModel):
    sub: str  # Unique Google ID
    email: str
    name: str
    picture: Optional[str] = None

# ===== MODELS SAVING TO FIRESTORE =====
# class HumanEventData(BaseModel):
#     #additional_kwargs: Optional[dict] = None
#     attachments: Optional[list[str]] = Field(None, description="List of file_ids attached to this human message")
#     #content : Optional[str] = None
#     #id : Optional[str] = None
#     #name : Optional[str] = None
#     #response_metadata : Optional[dict] = None

class ToolResultData(BaseModel):
    tool_name: str
    tool_args: dict
    data : Optional[dict] = None

# class AIEventData(BaseModel):
#     #content : Optional[str] = None
#     invalid_tool_calls : Optional[list] = None
#     token_stream: Optional[str] = None
#     tool_calls : Optional[list] = None

#     #additional_kwargs: Optional[dict] = None
#     #id : Optional[str] = None
#     #name : Optional[str] = None
#     #response_metadata : Optional[dict] = None
#     #type : str = "ai"
#     #usage_metadata : Optional[dict] = None

class EventData(BaseModel):
    attachments: Optional[list[str]] = Field(None, description="List of file_ids attached to this human message")
    invalid_tool_calls : Optional[list] = None
    tool_calls : Optional[list] = None
    token_stream: Optional[str] = None


class StreamEvent(BaseModel):
    order: int
    type: Literal["human", "ai", "tool_result"]
    created_at: datetime
    query_id: str
    event_id : str 
    session_id : str
    langchain_id: Optional[str] = None
    content : Optional[str] = None
    data : EventData | ToolResultData

class StreamData(BaseModel):
    llm_model : str
    project_id: Optional[str] = None
    title : Optional[str] = None
    last_updated : Optional[datetime] = None
    last_query_id : str
    events : list[StreamEvent]
    attachments : Optional[list[AttachmentModel]] = None



# def add_tool_results(existing: list, new: list) -> list:
#     return existing + new

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    factsheet : Optional[FactSheet | dict] = None
    attachments : Optional[list[Attachment] | list[dict]] = None #Annotated[list, add_tool_results]
