from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
import uuid

class Contact(BaseModel):
    name: str = Field(description="Full name of contact person")
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None

class Party(BaseModel):
    legal_name: str
    party_id : str = Field(default_factory = lambda : str(uuid.uuid4()))
    role: Literal["plaintiff", "defendant", "claimant", "respondent","witness", "expert","other"]
    entity_type: Literal["individual", "company", "government"]
    key_contact: Optional[Contact] = None
    legal_representation: Optional[str] = Field(
        None, description="Law firm representing this party"
    )

class Deadline(BaseModel):
    date: datetime
    description: str
    file_id: Optional[str] = Field(None, description="Related attachment reference")
    responsible_party: str

class Event(BaseModel):
    event_id: str = Field(default_factory = lambda : str(uuid.uuid4()))
    file_id: Optional[str] = Field(None, description="Related attachment reference")
    event_name: str
    date: datetime 
    description: str
    category: Literal[
        "contract_signed", "breach_occurred", "notice_sent", "payment_due",
        "payment_made", "termination", "meeting", "court_filing", "court_hearing",
        "settlement_offer", "deadline", "other"
    ]
    parties: list[str] = Field(description="Party_IDs of involved parties")
    significance: Literal["high", "medium", "low"]
    disputed: bool

class Events(BaseModel):
    events: list[Event]

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

class Claim(BaseModel):
    legal_basis: str = Field(description="Statutory basis (e.g., avtaleloven §36)")
    factual_basis: str = Field(description="Key facts supporting this claim")
    relief_sought: str = Field(description="What is being claimed (damages, injunction, etc)")
    strength_assessment: Literal["strong", "moderate", "weak"] = Field(
        description="Assessment of claim strength"
    )
    defense: Optional[str] = Field(None, description="Defense strategy if defending")
    party : str = Field(description="Party_ID of the claimant")

class Damage(BaseModel):
    category: Literal["direct_losses", "interest", "consequential", "punitive"]
    amount: Optional[int | float] = Field(None, description="Monetary amount if amount is known and mentioned, else None")
    basis: str
    supporting_evidence: list[str] = Field(description="File_IDs supporting the damage claim")
    party: str = Field(description="Party_ID of the claimant")

class InitialInput(BaseModel):
    # Factual background
    parties: list[Party]
    third_parties: list[Party]
    background: str
    title : str = Field(description="Title of the case or matter")

class AttachmentExtracted(BaseModel):    
    summary: str  = Field(description="Concise summary of the document content")
    key_provisions: Optional[list[str]] = Field(None, description="Important clauses or sections (for agreements)")
    #events: Optional[list[Event]] = Field(None, description="Key events mentioned in the document")
    party: Optional[list[Literal["plaintiff", "defendant", "claimant", "respondent","expert","witness","other"]]] = None
    date : Optional[datetime] = None
    category: Literal[
        "agreement", "correspondence", "meeting_minutes", "pleading", "evidence",
        "court_order", "invoice", "expert_report", "witness_statement", "internal_memo",
        "legal_opinion", "settlement_proposal", "power_of_attorney", "other"
    ]
    deadline: Optional[list[Deadline]] = Field(None, description="Relevant deadline if the document sets one")
    damage : Optional[list[Damage]] = Field(None, description="Damage information if applicable")
    claim : Optional[list[Claim]] = Field(None, description="Claim information if applicable")
    significance: Literal["high", "medium", "low"]

class Attachment(AttachmentExtracted):
    file_id: str = Field(default_factory = lambda : str(uuid.uuid4()))
    filename: str
    path: str 
    file_type: Literal["application/pdf", "text/plain", "application/msword",] #system generated
    size: int #system generated
    events: Optional[list[str]] = Field(None, description="event IDs mentioned in the document")


class FactualFacts(BaseModel):
    disputed_facts: list[str]
    undisputed_facts: list[str]

class FactSheet(InitialInput,FactualFacts):
    """Structured representation of case facts for legal analysis."""
    # Inherited from InitialInput
    #parties: list[Party]
    #third_parties: list[Party]
    #background: str = Field(description="A brief overview of the case background")

    # Inherited from FactualFacts
    #disputed_facts: list[str]
    #undisputed_facts: list[str]
    
    timeline: list[Event]
    
    # Law
    governing_law: GoverningLaw 
    
    # Claims
    claims: Optional[list[Claim]] = None
    # Damages
    damages: Optional[list[Damage]] = None
    # Deadlines
    deadlines: Optional[list[Deadline]] = None

    #metadata
    # case_id: str = Field(default_factory= lambda : str(uuid.uuid4()))
    # created_at: datetime = Field(default_factory=datetime.now().isoformat())
    # updated_at: datetime = Field(default_factory=datetime.now().isoformat())

class RelevanceCheck(BaseModel):
    is_relevant: bool
    reasoning: str