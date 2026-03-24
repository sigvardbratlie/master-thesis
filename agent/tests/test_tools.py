import pytest
import sys
import os
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.tools import _parse_date, show_elements, list_attachments, query_project_attachments, query_laws, read_attachments
from tests.fixtures.tools_data import (
    get_mock_factsheet,
    get_mock_claim,
    get_mock_damage,
    get_mock_event,
    get_mock_attachment,
    get_mock_email,
    get_mock_bq_doc,
)


# ============================================
#           UTILITY FUNCTIONS
# ============================================

def test_parse_date_none_returns_default():
    default = date(2020, 1, 1)
    assert _parse_date(None, default) == default.isoformat()


def test_parse_date_iso_string():
    assert _parse_date("2020-05-19", date.min) == "2020-05-19"


def test_parse_date_iso_string_with_time():
    assert _parse_date("2020-05-19T10:00:00", date.min) == "2020-05-19"


def test_parse_date_date_object():
    d = date(2021, 3, 15)
    assert _parse_date(d, date.min) == "2021-03-15"


def test_parse_date_datetime_object():
    dt = datetime(2021, 3, 15, 12, 0)
    assert _parse_date(dt, date.min) == "2021-03-15"


# ============================================
#           SHOW ELEMENTS — CLAIMS
# ============================================

def test_show_elements_claims_format(mock_sm_factory):
    factsheet = get_mock_factsheet(include_claims=True)
    mock_sm = mock_sm_factory(factsheet)

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = show_elements.invoke({"project_id": "project-001", "element_types": ["claims"]})

    assert "party_role" in result or "plaintiff" in result
    assert "Heving av kjøpet" in result
    assert "avhl. § 3-9" in result
    assert "strong" in result


def test_show_elements_claims_excludes_low_significance():
    high_claim = get_mock_claim(significance="high")

    mock_sm = MagicMock()
    # Simulate DB returning only high-significance claims
    mock_sm.load_elements.return_value = {"claims": [high_claim.model_dump()]}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = show_elements.invoke({
            "project_id": "project-001",
            "element_types": ["claims"],
            "significance": ["high"],
        })

    assert "Heving av kjøpet" in result
    assert "Prisavslag" not in result


# ============================================
#           SHOW ELEMENTS — DAMAGES
# ============================================

def test_show_elements_damages_format(mock_sm_factory):
    factsheet = get_mock_factsheet(include_damages=True)
    mock_sm = mock_sm_factory(factsheet)

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = show_elements.invoke({"project_id": "project-001", "element_types": ["damages"]})

    assert "plaintiff" in result
    assert "direct_losses" in result
    assert "500000" in result
    assert "NOK" in result
    assert "Utbedringskostnader betongdekke" in result


# ============================================
#           SHOW ELEMENTS — EVENTS
# ============================================

def test_show_elements_events_format(mock_sm_factory):
    factsheet = get_mock_factsheet(include_events=True)
    mock_sm = mock_sm_factory(factsheet)

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = show_elements.invoke({"project_id": "project-001", "element_types": ["events"]})

    assert "Forbehold om heving sendt" in result
    assert "2020-05-19" in result
    assert "file-001" in result


def test_show_elements_events_date_filter():
    mock_sm = MagicMock()
    # Simulate DB returning no events in the 2020 date range (both 2019 and 2021 filtered out)
    mock_sm.load_elements.return_value = {"events": []}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = show_elements.invoke({
            "project_id": "project-001",
            "element_types": ["events"],
            "start_date": "2020-01-01",
            "end_date": "2020-12-31",
        })

    assert "Forbehold om heving sendt" not in result
    assert "Forlik inngått" not in result


# ============================================
#           SHOW ELEMENTS — PARTIES
# ============================================

def test_show_elements_parties_format(mock_sm_factory):
    factsheet = get_mock_factsheet(include_parties=True)
    mock_sm = mock_sm_factory(factsheet)

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = show_elements.invoke({"project_id": "project-001", "element_types": ["parties"]})

    assert "Anders Kristiansen" in result
    assert "plaintiff" in result
    assert "individual" in result


# ============================================
#           LIST ATTACHMENTS — ATTACHMENTS
# ============================================

def test_list_attachments_format():
    attachment = get_mock_attachment()
    mock_sm = MagicMock()
    mock_sm.load_attachments.return_value = {"attachments": [attachment.model_dump()], "emails": []}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = list_attachments.invoke({
            "project_id": "project-001",
            "element_types": ["attachments"],
        })

    assert "file-001" in result
    assert "Forbehold om heving 2020-05-19" in result
    assert "correspondence" in result
    assert "2020-05-19" in result


def test_list_attachments_significance_filter():
    attachment_high = get_mock_attachment(significance="high")
    attachment_high.title = "Viktig dokument"
    mock_sm = MagicMock()
    # Simulate DB returning only high-significance items
    mock_sm.load_attachments.return_value = {"attachments": [attachment_high.model_dump()], "emails": []}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = list_attachments.invoke({
            "project_id": "project-001",
            "element_types": ["attachments"],
            "significance": ["high"],
        })

    assert "Viktig dokument" in result
    assert "Uviktig dokument" not in result


# ============================================
#           LIST ATTACHMENTS — EMAILS
# ============================================

def test_list_attachments_emails_format():
    email = get_mock_email()
    mock_sm = MagicMock()
    mock_sm.load_attachments.return_value = {"attachments": [], "emails": [email.model_dump()]}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = list_attachments.invoke({
            "project_id": "project-001",
            "element_types": ["emails"],
        })

    assert "email-001" in result
    assert "advokat@juridiskbyra.no" in result
    assert "E-post forbehold om heving" in result
    # "to" field should not be present since it was removed from format_map
    assert "carl@danielsen.no" not in result


def test_list_attachments_emails_date_filter():
    email_new = get_mock_email(email_date=datetime(2021, 3, 1, 10, 0))
    email_new.title = "Ny e-post"
    mock_sm = MagicMock()
    # Simulate DB returning only emails in the 2021 date range
    mock_sm.load_attachments.return_value = {"attachments": [], "emails": [email_new.model_dump()]}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm):
        result = list_attachments.invoke({
            "project_id": "project-001",
            "element_types": ["emails"],
            "start_date": "2021-01-01",
            "end_date": "2021-12-31",
        })

    assert "Gammel e-post" not in result
    assert "Ny e-post" in result


# ============================================
#           QUERY PROJECT ATTACHMENTS
# ============================================

def test_query_project_attachments_returns_results():
    mock_doc = get_mock_bq_doc(content="Betongdekket har alvorlige mangler")
    mock_vs = MagicMock()
    mock_vs.query.return_value = [mock_doc]

    with patch('agent.tools.BQVectorStore', return_value=mock_vs):
        result = query_project_attachments.invoke({
            "query": "mangler betongdekke",
            "project_id": "project-001",
        })

    assert "Betongdekket har alvorlige mangler" in result
    assert "test.pdf" in result
    mock_vs.query.assert_called_once()


def test_query_project_attachments_no_results():
    mock_vs = MagicMock()
    mock_vs.query.return_value = []

    with patch('agent.tools.BQVectorStore', return_value=mock_vs):
        result = query_project_attachments.invoke({
            "query": "ukjent tema",
            "project_id": "project-001",
        })

    assert "No relevant information found" in result


def test_query_project_attachments_with_metadata_filter():
    mock_doc = get_mock_bq_doc(file_id="file-abc")
    mock_vs = MagicMock()
    mock_vs.query.return_value = [mock_doc]

    with patch('agent.tools.BQVectorStore', return_value=mock_vs):
        result = query_project_attachments.invoke({
            "query": "lekkasje",
            "project_id": "project-001",
            "metadata": {"file_id": "file-abc"},
        })

    call_kwargs = mock_vs.query.call_args
    filters_passed = call_kwargs[1].get("filters") or call_kwargs[0][2] if call_kwargs[0] else {}
    assert "file-abc" in result


# ============================================
#           QUERY LAWS
# ============================================

def test_query_laws_returns_results():
    mock_doc = Document(
        page_content="Selger er ansvarlig for mangler etter avhendingsloven.",
        metadata={
            "title": "Avhendingslova",
            "short_title": "avhl.",
            "paragraph_number": "§ 3-9",
            "legal_area": "eiendom",
        },
    )
    mock_vs = MagicMock()
    mock_vs.query.return_value = [mock_doc]

    with patch('agent.tools.BQVectorStore', return_value=mock_vs):
        result = query_laws.invoke({"query": "mangler ved eiendomskjøp"})

    assert "Avhendingslova" in result
    assert "§ 3-9" in result
    assert "Selger er ansvarlig" in result


def test_query_laws_no_results():
    mock_vs = MagicMock()
    mock_vs.query.return_value = []

    with patch('agent.tools.BQVectorStore', return_value=mock_vs):
        result = query_laws.invoke({"query": "ukjent rettsområde"})

    assert "Ingen" in result or "ingen" in result


# ============================================
#           READ ATTACHMENTS
# ============================================

def test_read_attachments_returns_content():
    mock_sm = MagicMock()
    mock_sm.get_body_by_id.return_value = [
        {"body": "Innholdet i dokumentet", "path": "user/session/file-001.pdf"}
    ]

    mock_storage = MagicMock()

    with patch('agent.tools.SupabaseManager', return_value=mock_sm), \
         patch('agent.tools.SupabaseStorageManager', return_value=mock_storage):
        result = read_attachments.invoke({"ids": ["file-001"]})

    assert "Innholdet i dokumentet" in result


def test_read_attachments_missing_content():
    mock_sm = MagicMock()
    mock_sm.get_body_by_id.return_value = [
        {"body": None, "path": "user/session/file-999.pdf"}
    ]

    mock_storage = MagicMock()
    mock_storage.read_attachments.return_value = {"user/session/file-999.pdf": None}

    with patch('agent.tools.SupabaseManager', return_value=mock_sm), \
         patch('agent.tools.SupabaseStorageManager', return_value=mock_storage):
        result = read_attachments.invoke({"ids": ["file-999"]})

    assert "No content found" in result


# ============================================
#           FIXTURES
# ============================================

@pytest.fixture
def mock_sm_factory():
    def _factory(factsheet):
        mock_sm = MagicMock()
        mock_sm.load_factsheet.return_value = factsheet
        mock_sm.load_elements.return_value = {
            "claims": [c.model_dump() for c in factsheet.claims],
            "damages": [d.model_dump() for d in factsheet.damages],
            "events": [e.model_dump() for e in factsheet.events],
            "parties": [p.model_dump() for p in factsheet.parties],
            "deadlines": [dl.model_dump() for dl in factsheet.deadlines],
        }
        return mock_sm
    return _factory
