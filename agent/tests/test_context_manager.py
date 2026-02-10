import pytest
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from tests.fixtures.context_manager_data import get_mock_agent_state, get_mock_init_input
from tests.fixtures.supabase_data import get_mock_load_project_data
from tests.fixtures.email_data import get_mock_email_model_list, get_mock_email_extracted
import tiktoken
from agent.basemodels import *
from typing import List
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent.agent_modules import ContextManager

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
    result = await mock_context_manager.analyze_doc(initial_input=init_input,
                                                    content = "This is a test",
                                                    file_id="test_file_id",
                                                    filename="test_file_name",
                                                    path = "test_path",
                                                    file_type = "application/pdf",
                                                    size = 1024,
                                                    )

    mock_context_manager.llm.with_structured_output.assert_called_once()
    structured_llm.ainvoke.assert_called_once()
    assert isinstance(result, dict)
    assert "file" in result
    assert isinstance(result["file"], Attachment)
    assert "events" in result
    assert isinstance(result["events"], list)
    assert isinstance(result["events"][0], Event)
    assert result["events"][0].event_id, 'Shoudl be present'
    assert result["events"][0].file_id == "test_file_id"
    assert result["file"].path == "test_path"
    assert result["file"].file_id == "test_file_id"

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

async def test_consider_new_user_input(mock_context_manager):
    from tests.fixtures.context_manager_data import get_mock_factsheet
    structured_llm = AsyncMock()
    mock_context_manager.llm.with_structured_output.return_value = structured_llm
    factsheet = get_mock_factsheet()
    if not isinstance(factsheet, FactSheet):
         print(f"Factsheet is not of type FactSheet {type(factsheet)} | {factsheet}\ncheck the fixture data.")
    class AttachmentExtractedWithEvents(BaseModel):
            attachment: AttachmentExtracted
            events: List[Event]
    att = AttachmentExtracted(
        party_roles=["plaintiff"], 
        claims=factsheet.claims,
        deadlines=factsheet.deadlines,
        key_provisions=["prov1", "prov2"],
        description="description",
        file_date="2023-08-25",
        category="agreement",
        significance="high"
    )
         
    structured_llm.ainvoke.return_value = AttachmentExtractedWithEvents(events = factsheet.events, attachment=att)

    result = await mock_context_manager.consider_new_doc(factsheet = factsheet,
                                          new_content = "This is new content",
                                          new_user_input= "testinput",
                                          file_id = "test_file_id",
                                          filename = "test_filename",
                                          path = "test_path",
                                          file_type = "application/pdf",
                                          size = 1024)
    
    assert isinstance(result, dict)
    assert "file" in result
    assert isinstance(result["file"], Attachment)
    assert "events" in result
    assert isinstance(result["events"], list)
    assert isinstance(result["events"][0], Event)
    assert result["events"][0].event_id, 'Shoudl be present'
    assert result["events"][0].file_id == "test_file_id"
    assert result["file"].path == "test_path"
    assert result["file"].file_id == "test_file_id"
    assert result["file"].key_provisions == ["prov1", "prov2"]
    assert result["file"].description == "description"

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
        initial_input=init_input,
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
        initial_input=init_input,
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




