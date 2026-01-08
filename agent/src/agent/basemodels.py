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
    key_contact: Contact
    legal_representation: Optional[str] = Field(
        None, description="Law firm and key lawyers representing this party"
    )


class Deadline(BaseModel):
    date: datetime
    description: str
    file_id: Optional[str] = Field(None, description="Related document reference")
    responsible_party: str


class Event(BaseModel):
    event_id: str
    date: datetime 
    description: str
    file_id: Optional[str]
    category: Literal[
        "contract_signed", "breach_occurred", "notice_sent", "payment_due",
        "payment_made", "termination", "meeting", "court_filing", "court_hearing",
        "settlement_offer", "deadline", "other"
    ]
    parties: list[str] = Field(description="Party_IDs of involved parties")
    significance: Literal["high", "medium", "low"]
    disputed: bool


class Document(BaseModel):
    file_id: str 
    filename: str = Field(description="Original filename")
    path: str 
    summary: str 
    key_provisions: Optional[list[str]] = Field(None, description="Important clauses or sections (for agreements)")
    file_type: Literal["application/pdf", "text/plain", "application/msword",]
    size: int
    party: Literal["plaintiff", "defendant", "claimant", "respondent"]
    category: Literal[
        "agreement", "correspondence", "meeting_minutes", "pleading", "evidence",
        "court_order", "invoice", "expert_report", "witness_statement", "internal_memo",
        "legal_opinion", "settlement_proposal", "power_of_attorney", "other"
    ]
    event_id: str
    query_id: str
    deadline: Optional[Deadline]
    significance: Literal["high", "medium", "low"]

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


class Damage(BaseModel):
    category: Literal["direct_losses", "interest", "consequential", "punitive"]
    amount: int
    basis: str
    supporting_evidence: list[str]
    party: Party


class FactSheet(BaseModel):
    """Condensed case overview - detailed info stored in Document objects"""
    # Factual background
    parties: list[Party]
    third_parties: list[Party]
    background: str
    timeline: list[Event]
    disputed_facts: str
    undisputed_facts: str
    
    # Law
    governing_law: GoverningLaw 
    
    # Claims
    our_claims: list[Claim] 
    their_claims: list[Claim] 
    counter_claims: list[Claim] 
    # Damages
    damages: list[Damage]

    #metadata
    case_id: str = Field(default_factory= lambda : str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now().isoformat())
    updated_at: datetime = Field(default_factory=datetime.now().isoformat())