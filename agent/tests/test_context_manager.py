import logging
import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from tests.fixtures.context_manager_data import get_mock_agent_state, get_mock_init_input, get_mock_attachment_model, get_mock_attachment_model_list
from tests.fixtures.supabase_data import get_mock_load_project_data
from tests.fixtures.email_data import get_mock_email_model_list, get_mock_email_extracted, load_real_test_email
import tiktoken
from models import *
from pydantic import BaseModel
from utils import AppConfig

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
    manager = ContextManager(llm = llm_mock,
                             config = AppConfig())
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


def test_truncate_messages_removes_orphan_tool_messages_at_start(mock_context_manager):
    """Truncation should remove non-HumanMessages at the beginning after slicing."""
    from langchain_core.messages import ToolMessage
    messages = [
        HumanMessage(content="Q1"),
        AIMessage(content="A1", tool_calls=[{"name": "t", "args": {}, "id": "tc1"}]),
        ToolMessage(content="result1", tool_call_id="tc1", name="t"),
        AIMessage(content="A1 final"),
        HumanMessage(content="Q2"),
        AIMessage(content="A2"),
    ]
    # max_messages=3 takes last 3: [AIMessage(A1 final), HumanMessage(Q2), AIMessage(A2)]
    # then drops leading non-HumanMessage (AIMessage "A1 final"), leaving 2
    result = mock_context_manager.truncate_messages(messages, max_messages=3)
    assert len(result) == 2
    assert not any(isinstance(m, ToolMessage) for m in result)
    assert isinstance(result[0], HumanMessage)
    assert result[0].content == "Q2"


def test_truncate_messages_removes_trailing_ai_with_tool_calls(mock_context_manager):
    """Truncation should drop a trailing AIMessage that has tool_calls but no ToolMessage after."""
    messages = [
        HumanMessage(content="Q0"),
        AIMessage(content="A0"),
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
        HumanMessage(content="Q2"),
        AIMessage(content="A2", tool_calls=[{"name": "t", "args": {}, "id": "tc1"}]),
    ]
    # max_messages=3 takes last 3: [AIMessage(A1), HumanMessage(Q2), AIMessage(A2 with tool_calls)]
    # Then drops trailing AI with tool_calls
    result = mock_context_manager.truncate_messages(messages, max_messages=3)
    assert not (isinstance(result[-1], AIMessage) and result[-1].tool_calls)
    assert result[-1].content == "Q2"


def test_truncate_messages_keeps_tool_calls_with_response(mock_context_manager):
    """Truncation should keep AIMessage with tool_calls when ToolMessage follows (not at end)."""
    from langchain_core.messages import ToolMessage
    messages = [
        HumanMessage(content="Q1"),
        AIMessage(content="A1", tool_calls=[{"name": "t", "args": {}, "id": "tc1"}]),
        ToolMessage(content="result1", tool_call_id="tc1", name="t"),
        AIMessage(content="A1 final"),
    ]
    result = mock_context_manager.truncate_messages(messages, max_messages=4)
    assert len(result) == 4
    assert result[1].tool_calls  # AI with tool_calls preserved
    assert isinstance(result[2], ToolMessage)


def test_truncate_messages_no_truncation_needed(mock_context_manager):
    """When messages fit within max, return unchanged."""
    messages = [
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
    ]
    result = mock_context_manager.truncate_messages(messages, max_messages=5)
    assert len(result) == 2
    assert result == messages


def test_truncate_messages_orphan_tools_then_ai_at_start(mock_context_manager):
    """After removing orphan ToolMessages, first message should not be ToolMessage."""
    from langchain_core.messages import ToolMessage
    messages = [
        ToolMessage(content="orphan1", tool_call_id="tc0", name="t"),
        ToolMessage(content="orphan2", tool_call_id="tc1", name="t"),
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
        HumanMessage(content="Q2"),
        AIMessage(content="A2"),
    ]
    result = mock_context_manager.truncate_messages(messages, max_messages=4)
    # Last 4: [AIMessage(A1), HumanMessage(Q2), AIMessage(A2)] - wait that's only 3 after truncation
    # Actually last 4: [HumanMessage(Q1), AIMessage(A1), HumanMessage(Q2), AIMessage(A2)]
    assert not isinstance(result[0], ToolMessage)


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

def test_is_valid_uuid(mock_context_manager):
    valid = "123e4567-e89b-12d3-a456-426614174000"
    invalid = "not-a-uuid"
    almost_valid = "123e4567-e89b-12d3-a456-42661417400Z"  # Last character is not a valid hex digit
    assert mock_context_manager.is_valid_uuid(valid) == True
    assert mock_context_manager.is_valid_uuid(invalid) == False
    assert mock_context_manager.is_valid_uuid(almost_valid) == False

async def test_clean_elements(mock_context_manager):
    """clean_elements should return dict mapping element_type to cleaned list."""
    from tests.fixtures.context_manager_data import get_mock_clean_parties, get_mock_factsheet
    from pydantic import create_model, Field
    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    factsheet = get_mock_factsheet()
    project_data = ProjectData(factsheet=factsheet, attachments=[], emails=[])

    CombinedModel = create_model("CombinedElements", parties=(list[Party], Field(default_factory=list)))
    mock_response = CombinedModel(parties=get_mock_clean_parties())
    structured_llm.ainvoke.return_value = mock_response

    result = await mock_context_manager.clean_elements(element_types=["parties"], project_data=project_data)

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, dict)
    assert "parties" in result
    assert isinstance(result["parties"], list)


# ============================================
#     analyze_docs TESTS
# ============================================

async def test_analyze_docs_returns_dict(mock_context_manager):
    """analyze_docs should return a dict with attachments, events, damages, deadlines, claims."""
    init_input = get_mock_init_input()
    attachment_models = get_mock_attachment_model_list()

    class AttachmentWithEvents(BaseModel):
        attachment: AttachmentExtracted
        events: list[Event]

    class MultipleAttachmentsResult(BaseModel):
        attachments: list[AttachmentWithEvents]

    att1 = AttachmentExtracted(
        title="Purchase Agreement Granveien 15B",
        file_id="att-file-id-001",
        description="Purchase agreement for the property",
        significance="high",
        party_roles=["plaintiff", "defendant"],
        key_provisions=["Purchase price: NOK 15,500,000"],
        file_date="2023-08-25",
        category="agreement",
    )
    att2 = AttachmentExtracted(
        title="Seller Email House Condition",
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

    result = await mock_context_manager.analyze_docs(
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


async def test_analyze_docs_empty_list(mock_context_manager):
    """analyze_docs with empty attachment list should return empty results without calling LLM."""
    init_input = get_mock_init_input()

    result = await mock_context_manager.analyze_docs(
        input_=init_input,
        attachments=[],
    )

    mock_context_manager.llm.with_structured_output.assert_not_called()
    assert isinstance(result, dict)
    assert result["attachments"] == []
    assert result["events"] == []


async def test_analyze_docs_file_id_mismatch_fallback(mock_context_manager):
    """analyze_docs should use index-based fallback when LLM returns mismatched file_ids."""
    init_input = get_mock_init_input()
    attachment_models = get_mock_attachment_model_list()

    class AttachmentWithEvents(BaseModel):
        attachment: AttachmentExtracted
        events: list[Event]

    class MultipleAttachmentsResult(BaseModel):
        attachments: list[AttachmentWithEvents]

    # LLM returns wrong file_ids (hallucinated)
    att1 = AttachmentExtracted(
        title="Purchase Agreement",
        file_id="hallucinated-id-999",
        description="Purchase agreement",
        significance="high",
        party_roles=["plaintiff"],
        category="agreement",
    )
    att2 = AttachmentExtracted(
        title="Seller Email",
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

    result = await mock_context_manager.analyze_docs(
        input_=init_input,
        attachments=attachment_models,
    )

    # Should still produce valid results via index-based fallback
    assert len(result["attachments"]) == 2
    # file_id should be overridden from original input (not hallucinated)
    assert result["attachments"][0].file_id == "att-file-id-001"
    assert result["attachments"][1].file_id == "att-file-id-002"


# ============================================
#     analyze_emails TESTS
# ============================================

async def test_analyze_emails_returns_dict(mock_context_manager):
    """analyze_emails should return a dict with emails, events, damages, deadlines, claims."""
    init_input = get_mock_init_input()
    email_models = get_mock_email_model_list()
    mock_extracted = get_mock_email_extracted()

    # Build the expected LLM response structure
    class EmailAnalysisResult(BaseModel):
        email: EmailExtracted
        events: list[Event]
    class EmailsAnalysisResult(BaseModel):
        emails: list[EmailAnalysisResult]

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
                    title="Befaring Update",
                    description="Befaring update email",
                    significance="medium",
                    party_roles=["expert"],
                    deadlines=None,
                    damages=None,
                    claims=None,
                    key_points=["Befaring done"],
                    email_id="test-file-id-002",
                ),
                events=[]
            ),
        ]
    )

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = analysis_results

    result = await mock_context_manager.analyze_emails(
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


async def test_analyze_emails_empty_list(mock_context_manager):
    """analyze_emails with empty email list should still call LLM."""
    init_input = get_mock_init_input()

    class EmailAnalysisResult(BaseModel):
        email: EmailExtracted
        events: list[Event]
    class EmailsAnalysisResult(BaseModel):
        emails: list[EmailAnalysisResult]

    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    structured_llm.ainvoke.return_value = EmailsAnalysisResult(emails=[])

    result = await mock_context_manager.analyze_emails(
        input_=init_input,
        emails=[],
    )

    assert isinstance(result, dict)
    assert result["emails"] == []
    assert result["events"] == []


# ============================================
#      INTEGRATION TESTS (with real LLM)
# ============================================

@pytest.mark.asyncio
@pytest.mark.integration
async def test_analyze_emails_real_data_integration():
    """Integration test: analyze_emails with real EML file and real LLM"""
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file, including LLM API keys
    if not os.getenv("GOOGLE_API_KEY"):
        print(f' \n\n==== NOT FOUND GOOGLE_API_KEY in environment variables, skipping integration test. Set GOOGLE_API_KEY in .env file to run this test. ====\n\n')
    
    cm = ContextManager(config=AppConfig)  # Real LLM, not mocked
    
    # Load real email from test-file.eml
    test_email = load_real_test_email()
    
    # Create initial input
    initial_input = InitialInput(
        parties=[],
        background="Testing email analysis with real data",
        title="Integration Test Case"
    )
    
    # Run analysis with real LLM
    result = await cm.analyze_emails(
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
async def test_analyze_emails_multiple_emails_integration():
    """Integration test: analyze_emails with multiple mock emails"""
    from dotenv import load_dotenv
    load_dotenv()  # Load environment variables from .env file, including LLM API keys
    if not os.getenv("GOOGLE_API_KEY"):
        print(f' \n\n==== NOT FOUND GOOGLE_API_KEY in environment variables, skipping integration test. Set GOOGLE_API_KEY in .env file to run this test. ====\n\n')
    cm = ContextManager(config = AppConfig)  # Real LLM
    
    # Use mock emails (faster than parsing multiple real EMLs)
    emails = get_mock_email_model_list()
    
    initial_input = InitialInput(
        parties=[],
        background="Multi-email integration test",
        title="Multi-Email Test"
    )
    
    result = await cm.analyze_emails(
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




