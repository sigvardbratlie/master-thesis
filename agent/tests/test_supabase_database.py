import pytest
import httpx
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from tests.fixtures.supabase_data import *

# Legg til src-mappen i path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database import SupabaseManager


@pytest.fixture
def mock_supabase_manager():
    """
    Pytest fixture som oppretter en SupabaseManager med en mocket Supabase-klient.
    
    Eksempel bruk:
    def test_something(mock_supabase_manager):
        # mock_supabase_manager er allerede konfigurert
        pass
    """
    with patch('database.database_modules.create_client') as mock_create:
        mock_client = MagicMock()
        mock_create.return_value = mock_client
        manager = SupabaseManager()  
        manager.supabase = mock_client  
        yield manager 
        manager.supabase.reset_mock() 


def test_load_project(mock_supabase_manager):  
   #project = self.supabase.table("projects").select(select_query).eq("project_id", project_id).single().execute()


    #set responsee
    client = mock_supabase_manager.supabase
    mock_response = Mock()
    mock_response.data = get_mock_load_project_data().get("data")
    client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_response
    
    # call load_project
    project_id = 'ce119cd7-2c72-4400-8133-a08888b747ff'
    result = mock_supabase_manager.load_project(project_id)
    
    
    # === ASSERTIONS ===
    client.table.assert_called_once_with("projects")
    
    assert result is not None
    assert result.factsheet is not None
    assert result.attachments is not None

    factsheet = result.factsheet
    assert factsheet.project_id == project_id
    assert factsheet.title == 'Eiendomskjøpssak - Problemer med eiendommen'
    assert len(factsheet.parties) == 12

    attachments = result.attachments
    assert len(attachments) == 22


def test_save_project(mock_supabase_manager):
    data = get_mock_save_project_data()

    mock_supabase_manager.save_project(factsheet=data["factsheet"],
                                       attachments=data["attachments"],
                                       user_id="test_user_id", project_id="test_project_id",
                                       session_id="test_session_id", query_id="test_query_id",
                                       llm_model="test_model")

    client = mock_supabase_manager.supabase
    calls = client.table.return_value.upsert.call_args_list
    first_call_args = calls[0][0][0]
    assert first_call_args['project_id'] == "test_project_id"
    assert first_call_args['user_id'] == "test_user_id"
    assert first_call_args['created_by'] == "test_model"
    assert first_call_args['updated_by'] == "test_model"
    assert 'updated_at' in first_call_args
    assert client.table.call_count == 7


def test_save_project_with_party_reps(mock_supabase_manager):
    """save_project should upsert party_reps to project_party_reps when parties have reps."""
    from models import FactSheet, Party, PartyRep, Attachment

    party_rep = PartyRep(
        party_rep_id="rep-001",
        first_name="Erik",
        last_name="Advokatsen",
        rep_role="lawyer",
        party_id="party-001",
    )
    factsheet = FactSheet(
        events=[],
        parties=[
            Party(
                party_id="party-001",
                legal_name="Anders Kristiansen",
                role="plaintiff",
                entity_type="individual",
                party_reps=[party_rep],
            ),
            Party(
                party_id="party-002",
                legal_name="Carl Danielsen",
                role="defendant",
                entity_type="individual",
            ),
        ],
    )

    client = mock_supabase_manager.supabase
    client.reset_mock()

    mock_supabase_manager.save_project(
        factsheet=factsheet,
        attachments=[],
        user_id="test_user_id",
        project_id="test_project_id",
        session_id="test_session_id",
        llm_model="test_model",
    )

    table_calls = [call[0][0] for call in client.table.call_args_list]
    assert "project_party_reps" in table_calls, "project_party_reps table should be called"
    assert "project_parties" in table_calls, "project_parties table should be called"

    # Collect all upserted data per table (table and upsert calls are in 1:1 order)
    all_upsert_calls = client.table.return_value.upsert.call_args_list
    data_by_table = {table: all_upsert_calls[i][0][0] for i, table in enumerate(table_calls)}

    # party_reps upsert should have party_id and audit fields set
    upserted_reps = data_by_table["project_party_reps"]
    assert len(upserted_reps) == 1
    assert upserted_reps[0]["party_rep_id"] == "rep-001"
    assert upserted_reps[0]["project_id"] == "test_project_id"
    assert upserted_reps[0]["created_by"] == "test_model"

    # parties upserted without party_reps field
    upserted_parties = data_by_table["project_parties"]
    for p in upserted_parties:
        assert "party_reps" not in p or p["party_reps"] is None


def test_insert_project_element(mock_supabase_manager):
    data = get_mock_save_project_data().get("factsheet").model_dump(mode = "json").get("parties")
    client = mock_supabase_manager.supabase
    client.reset_mock()

    mock_supabase_manager.insert_project_element(data=data,
                                                 project_id="test_project_id",
                                                 table_name="project_parties",
                                                 llm_model="test_model")

    assert client.table.called, "table() was never called"
    client.table.assert_any_call("project_parties")
    client.table.return_value.upsert.assert_called()
    client.table.return_value.upsert.return_value.execute.assert_called()
    client.table.return_value.upsert.assert_called()
    client.table.return_value.upsert.return_value.execute.assert_called()

    inserted_data = client.table.return_value.upsert.call_args[0][0]
    for item in inserted_data:
        assert item['created_by'] == "test_model"
        assert item['updated_by'] == "test_model"
        assert 'updated_at' in item


def test_replace_project_element(mock_supabase_manager):
    data = get_mock_save_project_data().get("factsheet").model_dump(mode = "json").get("parties")
    client = mock_supabase_manager.supabase
    client.reset_mock()

    # Mock SELECT: first 2 parties are "existing" with original created_by/created_at
    existing_party_ids = [data[0]["party_id"], data[1]["party_id"]]
    existing_response = Mock()
    existing_response.data = [
        {"party_id": existing_party_ids[0], "created_by": "original_model", "created_at": "2026-01-01T00:00:00"},
        {"party_id": existing_party_ids[1], "created_by": "original_model", "created_at": "2026-01-01T00:00:00"},
    ]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = existing_response

    mock_supabase_manager.replace_project_element(data=data,
                                                  project_id="test_project_id",
                                                  table_name="project_parties",
                                                  llm_model="test_model")

    assert client.table.called, "table() was never called"
    client.table.assert_any_call("project_parties")
    client.table.return_value.delete.assert_called()
    client.table.return_value.insert.assert_called()

    inserted_data = client.table.return_value.insert.call_args[0][0]
    for item in inserted_data:
        assert item['updated_by'] == "test_model"
        assert 'updated_at' in item
        if item['party_id'] in existing_party_ids:
            assert item['created_by'] == "original_model"
            assert item['created_at'] == "2026-01-01T00:00:00"
        else:
            assert item['created_by'] == "test_model"

def test_upsert_replace_project_element(mock_supabase_manager):
    """upsert_replace_project_element should call upsert (not insert) and delete stale items."""
    data = get_mock_save_project_data().get("factsheet").model_dump(mode="json").get("parties")
    client = mock_supabase_manager.supabase
    client.reset_mock()

    existing_party_ids = [data[0]["party_id"], data[1]["party_id"]]
    existing_response = Mock()
    existing_response.data = [
        {"party_id": existing_party_ids[0], "created_by": "original_model", "created_at": "2026-01-01T00:00:00"},
        {"party_id": existing_party_ids[1], "created_by": "original_model", "created_at": "2026-01-01T00:00:00"},
    ]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = existing_response

    mock_supabase_manager.upsert_replace_project_element(
        data=data,
        project_id="test_project_id",
        table_name="project_parties",
        llm_model="test_model",
    )

    client.table.assert_any_call("project_parties")
    client.table.return_value.upsert.assert_called()
    client.table.return_value.delete.assert_called()
    client.table.return_value.delete.return_value.eq.return_value.not_.in_.assert_called()

    upserted_data = client.table.return_value.upsert.call_args[0][0]
    for item in upserted_data:
        assert item["updated_by"] == "test_model"
        assert "updated_at" in item
        if item["party_id"] in existing_party_ids:
            assert item["created_by"] == "original_model"
            assert item["created_at"] == "2026-01-01T00:00:00"
        else:
            assert item["created_by"] == "test_model"


def test_upsert_replace_project_element_removes_stale_items(mock_supabase_manager):
    """Items in DB but not in new list should be excluded from upsert and covered by delete not_.in_."""
    data = get_mock_save_project_data().get("factsheet").model_dump(mode="json").get("parties")
    client = mock_supabase_manager.supabase
    client.reset_mock()

    stale_party_id = "stale-0000-0000-0000-000000000000"
    existing_response = Mock()
    existing_response.data = [
        {"party_id": stale_party_id, "created_by": "old_model", "created_at": "2025-01-01T00:00:00"},
    ]
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = existing_response

    mock_supabase_manager.upsert_replace_project_element(
        data=data,
        project_id="test_project_id",
        table_name="project_parties",
        llm_model="test_model",
    )

    upserted_data = client.table.return_value.upsert.call_args[0][0]
    upserted_ids = [item["party_id"] for item in upserted_data]
    assert stale_party_id not in upserted_ids

    not_in_ids = client.table.return_value.delete.return_value.eq.return_value.not_.in_.call_args[0][1]
    assert stale_party_id not in not_in_ids


def test_upsert_replace_project_element_no_data_skips(mock_supabase_manager):
    """Empty data should skip all DB calls."""
    client = mock_supabase_manager.supabase
    client.reset_mock()

    mock_supabase_manager.upsert_replace_project_element(
        data=[],
        project_id="test_project_id",
        table_name="project_parties",
        llm_model="test_model",
    )

    client.table.assert_not_called()


@pytest.mark.skip(reason="load_projects was removed from SupabaseManager and moved to the UI layer (database_service.py)")
def test_load_projects(mock_supabase_manager):
    client = mock_supabase_manager.supabase
    data = get_mock_user_projects()
    response = Mock()
    response.data = data.get("data")

    client.table.return_value.select.return_value.eq.return_value.execute.return_value = response

    user_id = "test_user_id"
    result = mock_supabase_manager.load_projects(user_id)

    client.table.assert_called_once_with("projects")
    assert len(result) == 4
    assert result[0].created_at > result[-1].created_at

@pytest.mark.skip(reason="load_project_sessions was removed from SupabaseManager and moved to the UI layer (database_service.py)")
def test_load_project_sessions(mock_supabase_manager):
    client = mock_supabase_manager.supabase
    data = get_mock_project_sessions()
    response = Mock()
    response.data = data.get("data")

    client.table.return_value.select.return_value.eq.return_value.execute.return_value = response

    project_id = "test_project_id"
    result = mock_supabase_manager.load_project_sessions(project_id)

    client.table.assert_called_once_with("sessions")
    assert len(result) == 2
    assert result[0].updated_at > result[-1].updated_at


@pytest.mark.skip(reason="load_user_sessions was removed from SupabaseManager and moved to the UI layer (database_service.py)")
def test_load_user_sessions(mock_supabase_manager):
    client = mock_supabase_manager.supabase
    data = get_mock_user_sessions()
    response = Mock()
    response.data = data.get("data")

    client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = response

    user_id = "test_user_id"
    result = mock_supabase_manager.load_user_sessions(user_id)
    client.table.assert_called_once_with("sessions")
    assert len(result) == 8
    assert result[0].updated_at > result[-1].updated_at

def test_load_session_history(mock_supabase_manager):
    # Her kan du implementere en test for load_session_history på samme måte
    data = get_mock_session_history()
    client = mock_supabase_manager.supabase
    session_id = "test_session_id"
    response = Mock()
    response.data = data.get("data")
    #response = self.supabase.table("sessions").select(query).eq("session_id", session_id).single().execute()
    client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = response
    result = mock_supabase_manager.load_session_history(session_id)

    client.table.assert_called_once_with("sessions")
    assert result.events is not None
    assert result.attachments is not None
    assert result.title is not None
    assert result.updated_at is not None
    assert result.llm_model is not None
    assert len(result.events) == 4
    assert len(result.attachments) == 1


def test_save_stream(mock_supabase_manager):
    data = get_mock_stream_data()

    response = Mock()
    response.data = [{'title': 'Hei Assistance Summary'}]
    client = mock_supabase_manager.supabase
    # response = self.supabase.table("sessions").select("title") .eq("session_id", session_id)  .limit(1)\.execute()
    # self.supabase.table("sessions").upsert({
    #             "session_id": session_id,
    #             "user_id": user_id,
    #             "title" : title,
    #             "project_id": data.project_id,
    #             "llm_model" : data.llm_model,}).execute()
    # self.supabase.table("session_events").insert(new_events).execute() if new_events else None
    # self.supabase.table("session_attachments").insert(new_attachments).execute() if new_attachments else None


    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = response

    mock_supabase_manager.save_stream(data=data, 
                                      user_id="test_user_id", 
                                      session_id="test_session_id", 
                                      ) 
    client.table.assert_called()
    assert client.table.call_count == 4
    assert client.table.call_args_list[0][0][0] == "sessions"
    assert client.table.return_value.select.called


# ============================================================
# Reconnect tests — _with_reconnect and _execute
# ============================================================

class TestReconnect:
    """
    Verify that both _with_reconnect and _execute handle stale HTTP/2 connections.

    The crash scenario: after 2+ minutes of LLM processing the Supabase HTTP/2
    connection goes idle and the server sends a GOAWAY frame, which httpx surfaces
    as httpx.RemoteProtocolError.  Previously only httpx.ReadError was caught, so
    the reconnect logic never fired and every save after a long operation failed.
    """

    @pytest.fixture
    def manager(self):
        with patch("database.database_modules.create_client") as mock_create:
            fresh_client = MagicMock()
            mock_create.return_value = fresh_client
            mgr = SupabaseManager()
            mgr.supabase = MagicMock()   # stale client
            mgr._fresh_client = fresh_client
            mgr._mock_create = mock_create
            yield mgr

    # ---- _execute ----

    @pytest.mark.parametrize("exc_type", [httpx.ReadError, httpx.RemoteProtocolError])
    def test_execute_retries_on_stale_connection(self, manager, exc_type):
        """_execute should reconnect and succeed on the second attempt."""
        call_count = {"n": 0}

        def flaky():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise exc_type("stale")
            return "ok"

        result = manager._execute(flaky)

        assert result == "ok"
        assert call_count["n"] == 2
        assert manager._mock_create.call_count == 2  # initial __init__ + reconnect

    @pytest.mark.parametrize("exc_type", [httpx.ReadError, httpx.RemoteProtocolError])
    def test_execute_raises_if_retry_also_fails(self, manager, exc_type):
        """_execute should not swallow the error when the retry also fails."""
        def always_fails():
            raise exc_type("still dead")

        with pytest.raises(exc_type):
            manager._execute(always_fails)

    def test_execute_does_not_catch_unrelated_errors(self, manager):
        """_execute must not suppress unexpected exceptions."""
        def boom():
            raise ValueError("unexpected")

        with pytest.raises(ValueError):
            manager._execute(boom)

    # ---- _with_reconnect (via upsert_replace_project_element) ----

    @pytest.mark.parametrize("exc_type", [httpx.ReadError, httpx.RemoteProtocolError])
    def test_with_reconnect_retries_on_stale_connection(self, manager, exc_type, supabase_save_data):
        """
        upsert_replace_project_element decorated with @_with_reconnect should
        reconnect and complete successfully when the first attempt raises a stale
        connection error (the real crash scenario).
        """
        data = supabase_save_data.get("factsheet").model_dump(mode="json").get("parties")

        stale_client = manager.supabase
        fresh_client = manager._fresh_client

        # Stale client raises on SELECT (first call inside the method)
        stale_client.table.return_value.select.return_value.eq.return_value.execute.side_effect = exc_type("goaway")

        # Fresh client succeeds for all calls
        ok_response = MagicMock()
        ok_response.data = []
        fresh_client.table.return_value.select.return_value.eq.return_value.execute.return_value = ok_response
        fresh_client.table.return_value.upsert.return_value.execute.return_value = ok_response
        fresh_client.table.return_value.delete.return_value.eq.return_value.not_.in_.return_value.execute.return_value = ok_response

        manager.upsert_replace_project_element(
            data=data,
            project_id="test_project_id",
            table_name="project_parties",
            llm_model="test_model",
        )

        # Reconnect fired: create_client called once more after __init__
        assert manager._mock_create.call_count == 2
        # Fresh client was used for the retry
        fresh_client.table.assert_called()

    @pytest.mark.parametrize("exc_type", [httpx.ReadError, httpx.RemoteProtocolError])
    def test_with_reconnect_raises_if_retry_also_fails(self, manager, exc_type, supabase_save_data):
        """If the retry also fails, the error must propagate."""
        data = supabase_save_data.get("factsheet").model_dump(mode="json").get("parties")

        # Both stale and fresh clients fail
        for client in (manager.supabase, manager._fresh_client):
            client.table.return_value.select.return_value.eq.return_value.execute.side_effect = exc_type("dead")

        with pytest.raises(exc_type):
            manager.upsert_replace_project_element(
                data=data,
                project_id="test_project_id",
                table_name="project_parties",
                llm_model="test_model",
            )


@pytest.fixture
def supabase_save_data():
    return get_mock_save_project_data()