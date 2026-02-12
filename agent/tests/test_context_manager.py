import logging
import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from tests.fixtures.context_manager_data import get_mock_agent_state, get_mock_init_input, get_mock_attachment_model, get_mock_attachment_model_list
from tests.fixtures.supabase_data import get_mock_load_project_data
from tests.fixtures.email_data import get_mock_email_model_list, get_mock_email_extracted, load_real_test_email
import tiktoken
from models import *
from typing import List
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent import ContextManager

logger = logging.getLogger(__name__)

@pytest.fixture
def mock_context_manager():
    """
    Pytest fixture som oppretter en ContextManager med mocket data.
    
    Eksempel bruk:
    def test_something(mock_context_manager):
        # mock_context_manager er allerede konfigurert
        pass
    """
    
    llm_mock = MagicMock()
    manager = ContextManager(llm = llm_mock)
    yield manager

def test_truncate_tokens(mock_context_manager):
    state = get_mock_agent_state()
    enc = tiktoken.encoding_for_model("gpt-4o-mini")
    org_token_count = sum(len(enc.encode(msg.content)) for msg in state)
    max_tokens = 500
    result = mock_context_manager.truncate_tokens(messages=state, max_tokens=max_tokens)
    token_count = 0
    for msg in result:
        token_count += len(enc.encode(msg.content))


    
    assert token_count < org_token_count
    assert len(result) < len(state)
    assert result[-1].content == state[-1].content

def test_truncate_messages(mock_context_manager):
    state = get_mock_agent_state()
    max_messages = 3
    result = mock_context_manager.truncate_messages(messages=state, max_messages=max_messages)
    
    assert len(result) <= max_messages
    assert len(result) < len(state)
    assert result[-1].content == state[-1].content


async def test_analyze_init_input(mock_context_manager):
    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = get_mock_init_input()
    result = await mock_context_manager.analyze_init_input("Hello, world!")

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, InitialInput)
    assert len(result.parties) == 3
    assert result.parties[0].legal_name == "Andreas Nilsen"
    assert isinstance(result.background, str)
    assert result.title == "Property Dispute - Granveien 15B (Defects after purchase)"

async def test_analyze_doc(mock_context_manager):
    from tests.fixtures.context_manager_data import analyzed_dict1
    init_input = get_mock_init_input()
    attachment_model = get_mock_attachment_model()
    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    class AttachmentWithEvents(BaseModel):
            attachment: AttachmentExtracted
            events: List[Event]

    att = AttachmentExtracted(
        party_roles=analyzed_dict1.get("party_roles"),
        claims=analyzed_dict1.get("claims"),
        deadlines=analyzed_dict1.get("deadlines"),
        key_provisions=analyzed_dict1.get("key_provisions"),
        description=analyzed_dict1.get("description"),
        file_date=analyzed_dict1.get("file_date"),
        category=analyzed_dict1.get("category"),
        significance=analyzed_dict1.get("significance")
    )
    event = Event(event_start_date="2023-08-25", description="Document received",
                  event_name = "DocumentReceived",
                  parties = ["plaintiff"],
                  significance="high",
                  disputed=False,
                  category="court_filing")
    structured_llm.ainvoke.return_value = AttachmentWithEvents(attachment=att, events=[event])
    result = await mock_context_manager.analyze_doc(input_=init_input,
                                                    attachment=attachment_model,
                                                    )

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, dict)
    assert "attachment" in result
    assert isinstance(result["attachment"], Attachment)
    assert "events" in result
    assert isinstance(result["events"], list)
    assert isinstance(result["events"][0], Event)
    assert result["events"][0].event_id, 'Should be present'
    assert result["events"][0].file_id == "test_file_id"
    assert result["attachment"].path == attachment_model.path
    assert result["attachment"].file_id == "test_file_id"
    assert result["attachment"].body == attachment_model.body


async def test_analyze_doc_empty_body(mock_context_manager):
    """analyze_doc with empty body should return empty results without calling LLM."""
    init_input = get_mock_init_input()
    attachment_model = get_mock_attachment_model()
    attachment_model.body = None  # No parsed content

    result = await mock_context_manager.analyze_doc(input_=init_input,
                                                    attachment=attachment_model)

    mock_context_manager.llm.with_structured_output.assert_not_called()
    assert result["attachment"] is None
    assert result["events"] == []
    assert result["damages"] == []
    assert result["claims"] == []
    assert result["deadlines"] == []

async def test_analyze_governing_law(mock_context_manager):
    from tests.fixtures.context_manager_data import rag, governing_law
    events = get_mock_load_project_data().get("data").get("project_events")
    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = governing_law
    result = await mock_context_manager.analyze_governing_law(rag_content_law=rag, events=events)

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, GoverningLaw)
    assert result.primary_jurisdiction == "Norwegian law"
    assert result.procedural_law == "forvaltningsloven"
    assert "Contract Law" in result.key_areas

def test_is_valid_uuid(mock_context_manager):
    valid = "123e4567-e89b-12d3-a456-426614174000"
    invalid = "not-a-uuid"
    almost_valid = "123e4567-e89b-12d3-a456-42661417400Z"  # Last character is not a valid hex digit
    assert mock_context_manager.is_valid_uuid(valid) == True
    assert mock_context_manager.is_valid_uuid(invalid) == False
    assert mock_context_manager.is_valid_uuid(almost_valid) == False

async def test_clean_element(mock_context_manager):
    from tests.fixtures.context_manager_data import get_mock_clean_parties, get_mock_factsheet
    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    parties = Parties(parties = get_mock_clean_parties())
    party_id1 = parties.parties[1].party_id
    party_id2 = parties.parties[2].party_id
    factsheet = get_mock_factsheet()

    structured_llm.ainvoke.return_value = parties
    result = await mock_context_manager.clean_element(content = parties, factsheet=factsheet,element_type="parties")

    assert isinstance(result, list)
    assert len(result) == 4
    assert isinstance(result[0], dict)
    assert result[-1].get("party_id") is not None


# ============================================
#     analyze_multiple_docs TESTS
# ============================================

async def test_analyze_multiple_docs_returns_dict(mock_context_manager):
    """analyze_multiple_docs should return a dict with attachments, events, damages, deadlines, claims."""
    init_input = get_mock_init_input()
    attachment_models = get_mock_attachment_model_list()

    class AttachmentWithEvents(BaseModel):
        attachment: AttachmentExtracted
        events: List[Event]

    class MultipleAttachmentsResult(BaseModel):
        attachments: List[AttachmentWithEvents]

    att1 = AttachmentExtracted(
        file_id="att-file-id-001",
        description="Purchase agreement for the property",
        significance="high",
        party_roles=["plaintiff", "defendant"],
        key_provisions=["Purchase price: NOK 15,500,000"],
        file_date="2023-08-25",
        category="agreement",
    )
    att2 = AttachmentExtracted(
        file_id="att-file-id-002",
        description="Email from seller about house condition",
        significance="medium",
        party_roles=["defendant"],
        key_provisions=["Heat pumps functional"],
        file_date="2023-08-21",
        category="correspondence",
    )
    event1 = Event(
        event_start_date="2023-08-25",
        description="Purchase agreement signed",
        event_name="AgreementSigned",
        parties=["plaintiff", "defendant"],
        significance="high",
        disputed=False,
        category="contract_signed",
    )

    analysis_result = MultipleAttachmentsResult(
        attachments=[
            AttachmentWithEvents(attachment=att1, events=[event1]),
            AttachmentWithEvents(attachment=att2, events=[]),
        ]
    )

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = analysis_result

    result = await mock_context_manager.analyze_multiple_docs(
        input_=init_input,
        attachments=attachment_models,
    )

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, dict)
    assert "attachments" in result
    assert "events" in result
    assert "damages" in result
    assert "deadlines" in result
    assert "claims" in result

    # Should have 2 attachments
    assert len(result["attachments"]) == 2
    assert isinstance(result["attachments"][0], Attachment)
    assert isinstance(result["attachments"][1], Attachment)

    # file_id should come from original input, not LLM
    assert result["attachments"][0].file_id == "att-file-id-001"
    assert result["attachments"][1].file_id == "att-file-id-002"

    # Metadata should come from original input
    assert result["attachments"][0].filename == "2023-08-25_kjøpekontrakt.txt"
    assert result["attachments"][0].body == attachment_models[0].body
    assert result["attachments"][1].filename == "2023-08-21_epost_selger.txt"

    # Events should have file_id and event_id assigned
    assert len(result["events"]) == 1
    assert result["events"][0].file_id == "att-file-id-001"
    assert result["events"][0].event_id is not None
    assert mock_context_manager.is_valid_uuid(result["events"][0].event_id)
    assert result["events"][0].email_id is None


async def test_analyze_multiple_docs_empty_list(mock_context_manager):
    """analyze_multiple_docs with empty attachment list should return empty results without calling LLM."""
    init_input = get_mock_init_input()

    result = await mock_context_manager.analyze_multiple_docs(
        input_=init_input,
        attachments=[],
    )

    mock_context_manager.llm.with_structured_output.assert_not_called()
    assert isinstance(result, dict)
    assert result["attachments"] is None
    assert result["events"] == []


async def test_analyze_multiple_docs_file_id_mismatch_fallback(mock_context_manager):
    """analyze_multiple_docs should use index-based fallback when LLM returns mismatched file_ids."""
    init_input = get_mock_init_input()
    attachment_models = get_mock_attachment_model_list()

    class AttachmentWithEvents(BaseModel):
        attachment: AttachmentExtracted
        events: List[Event]

    class MultipleAttachmentsResult(BaseModel):
        attachments: List[AttachmentWithEvents]

    # LLM returns wrong file_ids (hallucinated)
    att1 = AttachmentExtracted(
        file_id="hallucinated-id-999",
        description="Purchase agreement",
        significance="high",
        party_roles=["plaintiff"],
        category="agreement",
    )
    att2 = AttachmentExtracted(
        file_id="hallucinated-id-888",
        description="Email from seller",
        significance="medium",
        party_roles=["defendant"],
        category="correspondence",
    )

    analysis_result = MultipleAttachmentsResult(
        attachments=[
            AttachmentWithEvents(attachment=att1, events=[]),
            AttachmentWithEvents(attachment=att2, events=[]),
        ]
    )

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = analysis_result

    result = await mock_context_manager.analyze_multiple_docs(
        input_=init_input,
        attachments=attachment_models,
    )

    # Should still produce valid results via index-based fallback
    assert len(result["attachments"]) == 2
    # file_id should be overridden from original input (not hallucinated)
    assert result["attachments"][0].file_id == "att-file-id-001"
    assert result["attachments"][1].file_id == "att-file-id-002"


# ============================================
#     analyze_multiple_eml TESTS
# ============================================

async def test_analyze_multiple_eml_returns_dict(mock_context_manager):
    """analyze_multiple_eml should return a dict with emails, events, damages, deadlines, claims."""
    init_input = get_mock_init_input()
    email_models = get_mock_email_model_list()
    mock_extracted = get_mock_email_extracted()

    # Build the expected LLM response structure
    class EmailAnalysisResult(BaseModel):
        email: EmailExtracted
        events: List[Event]
    class EmailsAnalysisResult(BaseModel):
        emails: List[EmailAnalysisResult]

    event = Event(
        event_start_date=datetime(2024, 1, 15),
        description="Email received about property case",
        event_name="EmailReceived",
        parties=["plaintiff"],
        significance="medium",
        disputed=False,
        category="communication"
    )

    analysis_results = EmailsAnalysisResult(
        emails=[
            EmailAnalysisResult(email=mock_extracted, events=[event]),
            EmailAnalysisResult(
                email=EmailExtracted(
                    description="Befaring update email",
                    significance="medium",
                    party_roles=["expert"],
                    deadlines=None,
                    damages=None,
                    claims=None,
                    key_points=["Befaring done"],
                    privilege_status=None,
                    email_id="test-file-id-002",
                ),
                events=[]
            ),
        ]
    )

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = analysis_results

    result = await mock_context_manager.analyze_multiple_eml(
        input_=init_input,
        emails=email_models,
    )

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, dict)
    assert "emails" in result
    assert "events" in result
    assert "damages" in result
    assert "deadlines" in result
    assert "claims" in result


async def test_analyze_multiple_eml_empty_list(mock_context_manager):
    """analyze_multiple_eml with empty email list should still call LLM."""
    init_input = get_mock_init_input()

    class EmailAnalysisResult(BaseModel):
        email: EmailExtracted
        events: List[Event]
    class EmailsAnalysisResult(BaseModel):
        emails: List[EmailAnalysisResult]

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = EmailsAnalysisResult(emails=[])

    result = await mock_context_manager.analyze_multiple_eml(
        input_=init_input,
        emails=[],
    )

    assert isinstance(result, dict)
    assert result["emails"] == []
    assert result["events"] == []


async def test_analyze_factual_facts(mock_context_manager):
    """analyze_factual_facts should return FactualFacts object."""
    init_input = get_mock_init_input()
    events = [
        Event(
            event_start_date=datetime(2024, 1, 15),
            description="Property dispute initiated",
            event_name="DisputeStart",
            parties=["plaintiff", "defendant"],
            significance="high",
            disputed=True,
            category="court_filing"
        )
    ]

    mock_facts = FactualFacts(
        disputed_facts=["Claim about defects disputed"],
        undisputed_facts=["Property was purchased in 2023"]
    )

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = mock_facts

    result = await mock_context_manager.analyze_factual_facts(
        initial_input=init_input,
        events=events,
    )

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, FactualFacts)
    assert len(result.disputed_facts) == 1
    assert len(result.undisputed_facts) == 1


# ============================================
#      INTEGRATION TESTS (with real LLM)
# ============================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_analyze_multiple_eml_real_data_integration():
    """Integration test: analyze_multiple_eml with real EML file and real LLM"""
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file, including LLM API keys
    if not os.getenv("GOOGLE_API_KEY"):
        print(f' \n\n==== NOT FOUND GOOGLE_API_KEY in environment variables, skipping integration test. Set GOOGLE_API_KEY in .env file to run this test. ====\n\n')
    
    cm = ContextManager()  # Real LLM, not mocked
    
    # Load real email from test-file.eml
    test_email = load_real_test_email()
    
    # Create initial input
    initial_input = InitialInput(
        parties=[],
        background="Testing email analysis with real data",
        title="Integration Test Case"
    )
    
    # Run analysis with real LLM
    result = await cm.analyze_multiple_eml(
        input_=initial_input,
        emails=[test_email]
    )
    print(f"\n\nIntegration test result\n\n: {result.get("emails")}\n\n {result.get("events")}\n\n {result.get("damages")}\n\n {result.get("deadlines")}\n\n {result.get("claims")}\n\n")
    # Validate structure
    assert "emails" in result
    assert "events" in result
    assert "damages" in result
    assert "deadlines" in result
    assert "claims" in result
    
    # Validate we got back 1 email
    assert len(result["emails"]) >= 1, "Should process at least 1 email"
    
    # Validate email_id matches
    processed_email = result["emails"][0]
    assert processed_email.email_id == test_email.file_id, f"Email ID mismatch: {processed_email.email_id} != {test_email.file_id}"
    
    # Validate all damages have file_id and unique damage_id
    for damage in result["damages"]:
        assert damage.email_id == test_email.file_id, f"Damage file_id mismatch"
        assert damage.damage_id is not None, "Damage should have damage_id"
        assert cm.is_valid_uuid(damage.damage_id), f"Invalid damage_id UUID: {damage.damage_id}"
    
    # Validate all deadlines have file_id and unique deadline_id
    for deadline in result["deadlines"]:
        assert deadline.email_id == test_email.file_id, f"Deadline file_id mismatch"
        assert deadline.deadline_id is not None, "Deadline should have deadline_id"
        assert cm.is_valid_uuid(deadline.deadline_id), f"Invalid deadline_id UUID: {deadline.deadline_id}"
    
    # Validate all claims have file_id and unique claim_id
    for claim in result["claims"]:
        assert claim.email_id == test_email.file_id, f"Claim file_id mismatch"
        assert claim.claim_id is not None, "Claim should have claim_id"
        assert cm.is_valid_uuid(claim.claim_id), f"Invalid claim_id UUID: {claim.claim_id}"
    
    # Validate all events have file_id and unique event_id
    for event in result["events"]:
        assert event.email_id == test_email.file_id, f"Event file_id mismatch"
        assert event.event_id is not None, "Event should have event_id"
        assert cm.is_valid_uuid(event.event_id), f"Invalid event_id UUID: {event.event_id}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_analyze_multiple_eml_multiple_emails_integration():
    """Integration test: analyze_multiple_eml with multiple mock emails"""
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file, including LLM API keys
    if not os.getenv("GOOGLE_API_KEY"):
        print(f' \n\n==== NOT FOUND GOOGLE_API_KEY in environment variables, skipping integration test. Set GOOGLE_API_KEY in .env file to run this test. ====\n\n')
    cm = ContextManager()  # Real LLM
    
    # Use mock emails (faster than parsing multiple real EMLs)
    emails = get_mock_email_model_list()
    
    initial_input = InitialInput(
        parties=[],
        background="Multi-email integration test",
        title="Multi-Email Test"
    )
    
    result = await cm.analyze_multiple_eml(
        input_=initial_input,
        emails=emails
    )
    
    # Should process all emails
    assert len(result["emails"]) <= len(emails), f"Should not return more emails than provided"
    
    # All returned emails should have valid file_ids matching input
    input_ids = {e.file_id for e in emails}
    for email in result["emails"]:
        assert email.email_id in input_ids, f"Email ID {email.email_id} not in original IDs {input_ids}"
    
    # All elements should have valid UUIDs
    all_file_ids = {e.file_id for e in emails}
    
    for damage in result["damages"]:
        assert damage.email_id in all_file_ids
        assert cm.is_valid_uuid(damage.damage_id)
    
    for deadline in result["deadlines"]:
        assert deadline.email_id in all_file_ids
        assert cm.is_valid_uuid(deadline.deadline_id)
    
    for claim in result["claims"]:
        assert claim.email_id in all_file_ids
        assert cm.is_valid_uuid(claim.claim_id)
    
    for event in result["events"]:
        assert event.email_id in all_file_ids
        assert cm.is_valid_uuid(event.event_id)




