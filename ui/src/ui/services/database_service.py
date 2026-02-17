import os
import logging
import streamlit as st
from typing import Optional
from supabase import create_client, Client
from ui.models import *
from ui.models import UserDetails, CompanyDetails

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

    def load_factsheet(self, project_id: str) -> dict:
        select_query = """
                *,
                project_events(*),
                project_parties(*),
                project_deadlines(*),
                project_damages(*),
                project_claims(*),
                project_legal(*)
                """
            
        project = self.supabase.table("projects").select(select_query).eq("project_id", project_id).single().execute()
        
        # Extract nested data from single query
        data = project.data
        project_events = data.pop("project_events", [])
        project_parties = data.pop("project_parties", [])
        project_deadlines = data.pop("project_deadlines", [])
        project_damages = data.pop("project_damages", [])
        project_claims = data.pop("project_claims", [])

        project_legal = data.pop("project_legal", {})
        project_legal.pop("created_at", None)
        project_legal.pop("project_id", None)

        factsheet = {}
        factsheet = dict(**data,
                              **project_legal,
                              parties=project_parties,
                              events=project_events,
                              deadlines=project_deadlines,
                              damages=project_damages,
                              claims=project_claims)
        return factsheet
    
    def load_project(self, project_id: str) -> dict:
        select_query = """
                *, 
                project_attachments(file_id, filename, file_type, path, created_at),
                project_events(*),
                project_parties(*),
                project_deadlines(*),
                project_damages(*),
                project_claims(*),
                project_legal(*),
                project_emails(email_id, from, to, cc, bcc, subject, body, date, created_at)
                """
            
        project = self.supabase.table("projects").select(select_query).eq("project_id", project_id).single().execute()
        
        # Extract nested data from single query
        data = project.data
        attachments = data.pop("project_attachments", [])
        project_events = data.pop("project_events", [])
        project_parties = data.pop("project_parties", [])
        project_deadlines = data.pop("project_deadlines", [])
        project_damages = data.pop("project_damages", [])
        project_claims = data.pop("project_claims", [])
        project_emails = data.pop("project_emails", [])

        project_legal = data.pop("project_legal", {})
        project_legal.pop("created_at", None)
        project_legal.pop("project_id", None)

        factsheet = {}
        factsheet = dict(**data,
                              **project_legal,
                              parties=project_parties,
                              events=project_events,
                              deadlines=project_deadlines,
                              damages=project_damages,
                              claims=project_claims)
        print(f'length of attachments: {len(attachments)} | len of emails {len(project_emails)}')
        return {
            "factsheet": factsheet,
            "attachments": attachments,
            "emails": project_emails
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
                                        .order("updated_at", desc=True)\
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
            session_events = self.supabase.table("session_events").select("*")\
                .eq("session_id", session_id)\
                .order("order", desc=False)\
                .execute()
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

    # ================== USER DETAILS ==================

    def load_user_details(self, user_id: str) -> Optional[UserDetails]:
        """Load user details from Supabase"""
        try:
            result = self.supabase.table("user_details").select("*").eq("user_id", user_id).execute()
            if result.data:
                return UserDetails.model_validate(result.data[0])
            return None
        except Exception as e:
            logger.error(f"Could not load user details for {user_id}: {e}")
            return None

    def upsert_user_details(self, user_details: UserDetails) -> bool:
        """Insert or update user details in Supabase"""
        try:
            data = user_details.model_dump(exclude_none=True)
            self.supabase.table("user_details").upsert(data, on_conflict="user_id").execute()
            return True
        except Exception as e:
            logger.error(f"Could not upsert user details: {e}")
            return False

    # ================== COMPANY DETAILS ==================

    def load_company_details(self, company_id: str) -> Optional[CompanyDetails]:
        """Load company details from Supabase"""
        try:
            result = self.supabase.table("company_details").select("*").eq("company_id", company_id).execute()
            if result.data:
                return CompanyDetails.model_validate(result.data[0])
            return None
        except Exception as e:
            logger.error(f"Could not load company details for {company_id}: {e}")
            return None

    def upsert_company_details(self, company_details: CompanyDetails) -> bool:
        """Insert or update company details in Supabase"""
        try:
            data = company_details.model_dump(exclude_none=True)
            self.supabase.table("company_details").upsert(data, on_conflict="company_id").execute()
            return True
        except Exception as e:
            logger.error(f"Could not upsert company details: {e}")
            return False

    def load_all_companies(self) -> list[CompanyDetails]:
        """Load all companies from Supabase"""
        try:
            result = self.supabase.table("company_details").select("*").execute()
            return [CompanyDetails.model_validate(c) for c in result.data]
        except Exception as e:
            logger.error(f"Could not load companies: {e}")
            return []

    
    def delete_project(self, project_id: str) -> bool:
        """Delete a project and all its related data from Supabase."""
        try:
            # First, get all attachment paths for this project
            attachments = self.supabase.table("project_attachments")\
                .select("path")\
                .eq("project_id", project_id)\
                .execute()
            
            # Delete all files from storage if any exist
            if attachments.data:
                paths = [att["path"] for att in attachments.data if att.get("path")]
                if paths:
                    self.delete_attachments(paths)
                    logger.info(f"Deleted {len(paths)} files from storage for project {project_id}")
            
            # Then delete from database (CASCADE will handle related tables)
            self.supabase.table("projects").delete().eq("project_id", project_id).execute()
            logger.info(f"Deleted project {project_id} from Supabase")
            return True
        except Exception as e:
            logger.error(f"Could not delete project {project_id}: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its related data from Supabase."""
        try:
            # First, get all attachment paths for this project
            attachments = self.supabase.table("session_attachments")\
                .select("path")\
                .eq("session_id", session_id)\
                .execute()
            
            # Delete all files from storage if any exist
            if attachments.data:
                paths = [att["path"] for att in attachments.data if att.get("path")]
                if paths:
                    self.delete_attachments(paths)
                    logger.info(f"Deleted {len(paths)} files from storage for session {session_id}")
        except Exception as e:
            logger.error(f"Could not delete attachments for session {session_id}: {e}")
            return False
        
        try:
            self.supabase.table("sessions").delete().eq("session_id", session_id).execute()
            logger.info(f"Deleted session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Could not delete session {session_id}: {e}")
            return False

    def delete_project_file(self, path : str) -> bool:
        """Delete a project file from Supabase storage."""
        try:
            self.supabase.storage.from_("attachments").remove(paths=[path])
            self.supabase.table("project_attachments").delete().eq("path", path).execute()
            logger.info(f"Deleted project file {path}")
            return True
        except Exception as e:
            logger.error(f"Could not delete project file {path}: {e}")
            return False

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
        
    def delete_attachments(self, paths : list[str], bucket_name: str = "attachments") -> bool:
        """Delete attachment from Supabase storage."""
        try:
            self.supabase.storage.from_(bucket_name).remove(paths=paths)
            logger.info(f"Deleted attachment {", ".join([p for p in paths])} from bucket {bucket_name}")
            return True
        except Exception as e:
            logger.error(f"Could not delete attachments {', '.join([p for p in paths])} from bucket {bucket_name}: {e}")
            return False
        
@st.cache_resource
def get_supabase_manager() -> SupabaseManager:
    """Cached SupabaseManager instance"""
    return SupabaseManager()