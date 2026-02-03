import os
import logging
import streamlit as st
from typing import Optional
from supabase import create_client, Client
from ui.models import * 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SupabaseManager:
    def __init__(self):
        self.url = st.secrets["SUPABASE_URL"]
        self.key = st.secrets["SUPABASE_KEY"]
        if not st.session_state.get("supabase_client"):
            st.session_state.supabase_client = create_client(self.url, self.key)
        self.supabase = st.session_state.supabase_client
        # Initialize Supabase client here if needed

    def load_project(self, project_id: str) -> dict:
        select_query = """
                *,
                project_attachments(*),
                project_events(*),
                project_parties(*),
                project_deadlines(*),
                project_damages(*),
                project_claims(*),
                project_custom(*)"""
            
        project = self.supabase.table("projects").select(select_query).eq("project_id", project_id).single().execute()
        
        # Extract nested data from single query
        data = project.data
        attachments = data.pop("project_attachments", [])
        project_events = data.pop("project_events", [])
        project_parties = data.pop("project_parties", [])
        project_deadlines = data.pop("project_deadlines", [])
        project_damages = data.pop("project_damages", [])
        project_claims = data.pop("project_claims", [])

        project_custom = data.pop("project_custom", {})
        project_custom.pop("created_at", None)
        project_custom.pop("project_id", None)

        factsheet = {}
        factsheet = dict(**data,
                              **project_custom,
                              parties=project_parties,
                              events=project_events,
                              deadlines=project_deadlines,
                              damages=project_damages,
                              claims=project_claims)
        return {
            "factsheet": factsheet,
            "attachments": attachments
        }

    def load_projects(self,user_id: str):
        projects = self.supabase.table("projects").select("project_id, title, created_at").eq("user_id", user_id).execute()
        if projects.data:
            # Sorter etter created_at (nyeste først)
            sorted_projects = sorted(
                projects.data, 
                key=lambda x: x.get("created_at") or "", 
                reverse=True
            )
            return sorted_projects
        return []

    def load_project_sessions(self,project_id: str, ):
        project_sessions = self.supabase.table("sessions").select("session_id, title, updated_at, llm_model").eq("project_id", project_id).execute()
        if project_sessions.data:
            # Sorter etter updated_at (nyeste først)
            sorted_sessions = sorted(
                project_sessions.data, 
                key=lambda x: x.get("updated_at") or "", 
                reverse=True
            )
            return [SessionInfo.model_validate(s) for s in sorted_sessions]
        return []

    def load_user_sessions(self, user_id: str)-> list:
        '''Load all sessions for a user from Supabase'''
        # Implement loading user sessions from Supabase
        try:
            sessions = self.supabase.table("sessions")\
                                        .select("title, session_id, updated_at")\
                                        .eq("user_id", user_id)\
                                        .order("updated_at", desc=False)\
                                        .execute()

            logger.debug(f'Loaded {len(sessions.data)} sessions for user {user_id} from Supabase.')
            return [SessionInfo.model_validate(s) for s in sessions.data]
        except Exception as e:
            logger.error(f'Could not load sessions for user {user_id} from Supabase: {e}')
            return []

    def load_session_history(self, session_id: str, 
                             #user_id: str = None
                             ) -> dict: #rm user_id
        '''Load session history for a given session from Supabase'''
        try:
            session_events = self.supabase.table("session_events").select("*").eq("session_id", session_id).execute()
        except Exception as e:
            logger.error(f'Could not load session events for session {session_id} from Supabase: {e}')
            return {"error": str(e)}
        try:    
            session_attachments = self.supabase.table("session_attachments").select("*").eq("session_id", session_id).execute()
        except Exception as e:
            logger.error(f'Could not load session attachments for session {session_id} from Supabase: {e}')
            return {"error": str(e)}
        try:
            session = self.supabase.table("sessions").select("*").eq("session_id", session_id).execute()
            logger.debug(f'Loaded session history for session {session_id} from Supabase.')
        except Exception as e:
            logger.error(f'Could not load session for session {session_id} from Supabase: {e}')
            return {"error": str(e)}
        
        session_data = session.data[0] if session.data else {}
        data = {
                "events": session_events.data,  
                'attachments': session_attachments.data,
                "project_id": session_data.get("project_id",""),
                "title": session_data.get("title",""), 
                "llm_model": session_data.get("llm_model"),
                "last_updated": session_data.get("updated_at"),
            }
        return SessionHistoryResponse.model_validate(data)

    def load_project_element(self, project_id: str, element_type: str) -> list:
        """
        Load project elements of a specific type from Supabase.
        """
        valid_element_types = ["attachments", "events", "parties", "deadlines", "damages", "claims", "custom"]
        if element_type not in valid_element_types:
            logger.error(f'Invalid element type requested: {element_type}')
            return []
        try:
            table_name = f"project_{element_type}"
            elements = self.supabase.table(table_name).select("*").eq("project_id", project_id).execute()
            logger.debug(f'Loaded {len(elements.data)} elements of type {element_type} for project {project_id} from Supabase.')
            return elements.data
        except Exception as e:
            logger.error(f'Could not load project elements of type {element_type} for project {project_id} from Supabase: {e}')
            return []

    def read_attachment(self, path : str, bucket_name : str = "attachments") -> Optional[bytes]:
        """
        Fetch attachment content from Supabase storage.
        """
        try:

            content = self.supabase.storage.from_(bucket_name).download(path)
            
            if content:
                return content
            else:
                logger.error(f'Attachment blob not found: {path}')
                return None

        except Exception as e:
            logger.error(f'Error reading attachment from Supabase: {e}', exc_info=True)
            return None
        
@st.cache_resource
def get_supabase_manager() -> SupabaseManager:
    """Cached SupabaseManager instance"""
    return SupabaseManager()