from datetime import date, datetime
from unittest.mock import MagicMock
from langchain_core.documents import Document
from models import (
    Claim, Damage, Event, Deadline, Party,
    Attachment, Email, FactSheet,
)


def get_mock_claim(significance="high", party_role="plaintiff") -> Claim:
    return Claim(
        claim_id="claim-001",
        legal_basis="avhl. § 3-9",
        factual_basis="Lekkasje i betongdekke",
        relief_sought="Heving av kjøpet",
        strength_assessment="strong",
        party_role=party_role,
        significance=significance,
    )


def get_mock_damage(significance="high", party_role="plaintiff") -> Damage:
    return Damage(
        damage_id="damage-001",
        category="direct_losses",
        amount=500000,
        currency="NOK",
        basis="Utbedringskostnader betongdekke",
        supporting_evidence=[],
        party_role=party_role,
        significance=significance,
    )


def get_mock_event(event_date: date = date(2020, 5, 19), significance="high") -> Event:
    return Event(
        event_id="event-001",
        file_id="file-001",
        event_name="Forbehold om heving sendt",
        event_start_date=event_date,
        description="Juridisk Byrå AS sendte forbehold om heving til selger",
        category="court_filing",
        significance=significance,
        disputed=False,
    )


def get_mock_deadline(significance="high") -> Deadline:
    return Deadline(
        deadline_id="deadline-001",
        deadline_date=date(2025, 6, 23),
        description="Hovedforhandling Rogaland Tingrett",
        file_id="file-002",
        email_id=None,
        significance=significance,
    )


def get_mock_party(significance="high") -> Party:
    return Party(
        legal_name="Anders Kristiansen",
        party_id="party-001",
        role="plaintiff",
        entity_type="individual",
        role_description="Saksøker og kjøper av eiendommen",
        significance=significance,
    )


def get_mock_factsheet(
    include_claims=True,
    include_damages=True,
    include_events=True,
    include_deadlines=True,
    include_parties=True,
) -> FactSheet:
    return FactSheet(
        project_id="project-001",
        title="Fjellveien 42A Eiendomstvist",
        background="Eiendomskjøp med mangler",
        parties=[get_mock_party()] if include_parties else [],
        events=[get_mock_event()] if include_events else [],
        claims=[get_mock_claim()] if include_claims else [],
        damages=[get_mock_damage()] if include_damages else [],
        deadlines=[get_mock_deadline()] if include_deadlines else [],
    )


def get_mock_attachment(significance="high", file_date: date = date(2020, 5, 19)) -> Attachment:
    return Attachment(
        file_id="file-001",
        filename="forbehold_heving.pdf",
        path="user/session/file-001.pdf",
        file_type="application/pdf",
        size=12345,
        title="Forbehold om heving 2020-05-19",
        category="correspondence",
        file_date=file_date,
        significance=significance,
        description="Brev med forbehold om heving av kjøpet",
    )


def get_mock_email(significance="high", email_date: datetime = datetime(2020, 5, 18, 10, 0)) -> Email:
    return Email(
        **{
            "from": "advokat@juridiskbyra.no",
            "to": ["carl@danielsen.no"],
            "subject": "Forbehold om heving",
            "date": email_date,
            "message-id": "<mock-message-id@juridiskbyra.no>",
            "body": "Herved meddeles forbehold om heving av eiendomskjøpet.",
            "email_id": "email-001",
            "title": "E-post forbehold om heving",
            "significance": significance,
            "description": "E-post med forbehold om heving",
        }
    )


def get_mock_bq_doc(file_id="file-001", filename="test.pdf", content="Relevant legal content") -> Document:
    return Document(
        page_content=content,
        metadata={
            "file_id": file_id,
            "filename": filename,
            "title": "Test document",
            "chunk": 1,
            "total_chunks": 1,
        },
    )
