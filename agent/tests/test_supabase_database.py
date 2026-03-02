import pytest
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

    #self.supabase.table("project_legal").upsert({**custom, "project_id": project_id}).execute()

    mock_supabase_manager.save_project(factsheet=data["factsheet"], 
                                       attachments=data["attachments"],
                                       user_id="test_user_id", project_id="test_project_id",
                                       session_id="test_session_id", query_id="test_query_id")
    
    client = mock_supabase_manager.supabase
    #client.reset_mock()
    calls = client.table.return_value.upsert.call_args_list
    first_call_args = calls[0][0][0]  # Første argument til første kall
    assert first_call_args['project_id'] == "test_project_id"
    assert first_call_args['user_id'] == "test_user_id"
    assert client.table.call_count == 7


def test_insert_project_element(mock_supabase_manager):
    data = get_mock_save_project_data().get("factsheet").model_dump(mode = "json").get("parties")
    client = mock_supabase_manager.supabase
    client.reset_mock()
    #self.supabase.table(table_name).insert(data).execute()

    mock_supabase_manager.insert_project_element(data=data ,
                                                 project_id="test_project_id",
                                                 table_name="project_parties")
    
    assert client.table.called, "table() was never called"
    client.table.assert_any_call("project_parties")
    client.table.return_value.insert.assert_called()
    client.table.return_value.insert.return_value.execute.assert_called()


def test_replace_project_element(mock_supabase_manager):
    data = get_mock_save_project_data().get("factsheet").model_dump(mode = "json").get("parties")
    client = mock_supabase_manager.supabase
    client.reset_mock()
    #self.supabase.table(table_name).insert(data).execute()

    mock_supabase_manager.replace_project_element(data=data ,
                                                 project_id="test_project_id",
                                                 table_name="project_parties")
    
    assert client.table.called, "table() was never called"
    client.table.assert_any_call("project_parties")
    client.table.return_value.insert.assert_called()
    client.table.return_value.insert.return_value.execute.assert_called()

def test_load_projects(mock_supabase_manager):
    client = mock_supabase_manager.supabase
    data = get_mock_user_projects()
    response = Mock()
    response.data = data.get("data")

    #projects = self.supabase.table("projects").select("project_id, title, created_at").eq("user_id", user_id).execute()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = response

    user_id = "test_user_id"
    result = mock_supabase_manager.load_projects(user_id)

    client.table.assert_called_once_with("projects")
    assert len(result) == 4
    assert result[0].created_at > result[-1].created_at

def test_load_project_sessions(mock_supabase_manager):
    client = mock_supabase_manager.supabase
    data = get_mock_project_sessions()
    response = Mock()
    response.data = data.get("data")
    #project_sessions = self.supabase.table("sessions").select("session_id, title, updated_at, llm_model").eq("project_id", project_id).execute()
    client.table.return_value.select.return_value.eq.return_value.execute.return_value = response

    project_id = "test_project_id"
    result = mock_supabase_manager.load_project_sessions(project_id)

    client.table.assert_called_once_with("sessions")
    assert len(result) == 2
    assert result[0].updated_at > result[-1].updated_at


def test_load_user_sessions(mock_supabase_manager):
    client = mock_supabase_manager.supabase
    data = get_mock_user_sessions()
    response = Mock()
    response.data = data.get("data")
    #sessions = self.supabase.table("sessions").select("title, session_id, updated_at").eq("user_id", user_id).order("updated_at", desc=True).execute()
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