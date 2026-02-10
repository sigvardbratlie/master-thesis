import os
import logging
import base64
from google.cloud import firestore

from supabase import create_client, Client

from models import *
from fastapi import FastAPI,HTTPException,status,Depends
from agent.agent_modules import Summarizer
import email 
from email.message import Message 

from datetime import datetime
from pydantic import BaseModel

import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class FirestoreManager:
    def __init__(self, db=None):
        self.db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database="(default)") if not db else db
        self.summarizer = Summarizer()
        
    def load_project(self, user_id: str, project_id: str):
        try:
            factsheet_ref = (
                self.db.collection("projects")
                .document(user_id)
                .collection("projects")
                .document(project_id)
            )
            
            factsheet_doc = factsheet_ref.get()
            
            if not factsheet_doc.exists:
                logger.warning(f"No factsheet found for project_id: {project_id}")
                return {"error": "Factsheet not found"}
            
            factsheet_data = factsheet_doc.to_dict()
            return factsheet_data
        
        except Exception as e:
            logger.error(f"Error loading factsheet: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    def load_projects(self,user_id: str):
        try:
            projects_ref = (
                self.db.collection("projects")
                .document(user_id)
                .collection("projects")
            )
            
            projects_docs = projects_ref.stream()
            
            all_projects = []
            
            for project_doc in projects_docs:
                project_data = project_doc.to_dict()
                project_id = project_doc.id
                
                all_projects.append({
                    "project_id": project_id,
                    "title": project_data.get("factsheet",{}).get("title", ""),
                    "created_at": project_data.get("created_at"),
                })
            
            # Sorter etter created_at (nyeste først)
            all_projects.sort(
                key=lambda x: x.get("created_at") or "", 
                reverse=True
            )
            
            return all_projects
        
        except Exception as e:
            logger.error(f'Could not load projects for user {user_id}: {e}', exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def load_user_sessions(self, user_id: str):
        try:
            # Hent alle sessions for brukeren
            sessions_ref = (
                self.db.collection("chat_history")
                .document(user_id)
                .collection("sessions")
            )
            
            sessions_docs = sessions_ref.stream()
            
            all_sessions = []
            
            for session_doc in sessions_docs:
                session_data = session_doc.to_dict()
                session_id = session_doc.id
                
                # Sjekk om session har events
                events = session_data.get("events", [])
                title = session_data.get("title", "")
                if not events:
                    continue  # Skip tomme sessions
                            
                # Hent timestamp for sortering
                timestamp = session_data.get("last_updated")
                
                all_sessions.append({
                    "session_id": session_id,
                    "title": title,
                    "timestamp": timestamp,
                    "llm_model": session_data.get("llm_model"),
                })
            
            # Sorter etter timestamp (nyeste først)
            all_sessions.sort(
                key=lambda x: x.get("timestamp") or "", 
                reverse=True
            )
            
            # Fjern timestamp fra response (ikke nødvendig for UI)
            for session in all_sessions:
                session.pop("timestamp", None)
            
            return all_sessions
        
        except Exception as e:
            logger.error(f'Could not load sessions for user {user_id}: {e}', exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    def load_session_history(self, session_id: str, user_id: str):
        try:
            session_ref = (
                self.db.collection("chat_history")
                .document(user_id)
                .collection("sessions")
                .document(session_id)
            )
            
            session_doc = session_ref.get()
            
            if not session_doc.exists:
                logger.warning(f"No session found for session_id: {session_id}")
                return {
                    "events": [],
                    "title": "Ny samtale",
                }
            
            session_data = session_doc.to_dict()
            
            events = session_data.get("events", [])
            title = session_data.get("title", "")
            
            if not events:
                return {
                    "events": [],
                    "title": "Ny samtale",
                }
            
            return {
                "events": events,  
                "title": title, 
                "llm_model": session_data.get("llm_model"),
                "last_updated": session_data.get("last_updated"),
            }
        
        except Exception as e:
            logger.error(f"Error loading session history: {e}", exc_info=True)
            return {"error": str(e)}

    def load_project_sessions(self, user_id: str, project_id: str):
        try:
            # Hent alle sessions for brukeren
            sessions_ref = (
                self.db.collection("chat_history")
                .document(user_id)
                .collection("sessions")
                .where("project_id", "==", project_id)
            )
            
            sessions_docs = sessions_ref.stream()
            
            all_sessions = []
            
            for session_doc in sessions_docs:
                session_data = session_doc.to_dict()
                session_id = session_doc.id
                
                # Sjekk om session har events
                events = session_data.get("events", [])
                title = session_data.get("title", "")
                if not events:
                    continue  # Skip tomme sessions
                            
                # Hent timestamp for sortering
                timestamp = session_data.get("last_updated")
                
                all_sessions.append({
                    "session_id": session_id,
                    "title": title,
                    "timestamp": timestamp,
                    "llm_model": session_data.get("llm_model"),
                })
            
            # Sorter etter timestamp (nyeste først)
            all_sessions.sort(
                key=lambda x: x.get("timestamp") or "", 
                reverse=True
            )
            
            # Fjern timestamp fra response (ikke nødvendig for UI)
            for session in all_sessions:
                session.pop("timestamp", None)
            
            return all_sessions
        
        except Exception as e:
            logger.error(f'Could not load sessions for user {user_id}: {e}', exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))


    def save_stream(self, 
                    data : StreamData,
                    user_id : str,
                    session_id : str): 
        ''' Save the final state of the conversation session to Firestore 
        
        
        '''
        
        new_events = [event.model_dump(mode = "json") for event in data.events] if data.events else None
        new_attachments = [attachment.model_dump(mode = "json") for attachment in data.attachments] if data.attachments else None

        try:
            # Fetch current session
            session_ref = self.db.collection("chat_history").document(user_id).collection("sessions").document(session_id)
            session_doc = session_ref.get() 
            
            # extract existing events
            if session_doc.exists:
                session_data =  session_doc.to_dict()
                all_events = session_data.get("events", [])
                all_attachments = session_data.get("attachments", [])
                title = session_data.get("title", "")
            else:
                all_events = []
                all_attachments = []
                title = ""

            if not title or title == "Ny samtale":
                try:
                    title_msg = [msg.get("content") for msg in new_events if msg.get("type") == "human" or msg.get("type") == "ai"]
                    logger.debug(f"Generating title from messages: {title_msg}")
                    #title = await self.mk_title(title_msg)
                    title = self.summarizer.mk_title(title_msg)
                except Exception as e:
                    logger.error(f"Error creating title: {e}", exc_info=True)
                    title = "Ny samtale"

            all_events.extend(new_events) if new_events else None
            all_attachments.extend(new_attachments) if new_attachments else None

             # Save updated session
            session_ref.set({
                "events": all_events, 
                "attachments": all_attachments,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "project_id": data.project_id,
                "llm_model": data.llm_model,
                "last_query_id": data.last_query_id,
                "title" : title
            })
            
            logger.debug(f"Session saved with {len(all_events)} total events")
        except Exception as e:
            logger.error(f"Error saving final state: {e}", exc_info=True)
    
    def save_project(self,
                       factsheet : FactSheet,
                       files  : list[Attachment],
                       user_id : str,
                       project_id : str,
                       session_id : str,
                       query_id : str = ""

                       ):
        ''' Save project to Firestore
        
        Args:
            factsheet (FactSheet): The factsheet object to save.
            files (list): List of attachment objects to save.

        Returns:
            None
        '''

        ref = self.db.collection("projects").document(user_id).collection("projects").document(project_id)
        try:
            ref.set({
                "user_id": user_id,
                "updated_session_id": session_id,
                "updated_query_id": query_id,
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "factsheet": factsheet.model_dump(mode='json'),
                "attachments": [file.model_dump(mode='json') for file in files]
            })
            logger.debug(f"Project saved for project {project_id}")
        except Exception as e:
            logger.error(f"Error saving project to firestore: {e}", exc_info=True)

    def get_or_create_user(self, google_user_info: dict) -> str:
        """
        Finds a user based on Google User ID, or creates a new one if it doesn't exist.
        Returns the app's internal user_id (document ID in Firestore).
        
        Args:
            google_user_info (dict): Dictionary containing Google user information with keys like 'sub', 'email', 'name', 'picture'.
        
        Returns:
            str: The internal user ID (Firestore document ID).
        """
        google_user_id = google_user_info['sub']

        # Sjekk om brukeren allerede finnes
        users_ref = self.db.collection("users")
        query = users_ref.where('google_user_id', '==', google_user_id).limit(1)
        existing_users = list(query.stream())

        if existing_users:
            # Brukeren finnes, returner ID-en
            user_doc = existing_users[0]
            return user_doc.id
        else:
            # Opprett en ny bruker
            new_user_data = {
                'google_user_id': google_user_id,
                'email': google_user_info.get('email'),
                'name': google_user_info.get('name'),
                'picture': google_user_info.get('picture'),
                'created_at': firestore.SERVER_TIMESTAMP
            }
            _, user_ref = users_ref.add(new_user_data)
            return user_ref.id



class SupabaseManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)
        # Initialize Supabase client here if needed

    def load_factsheet(self, project_id: str) -> FactSheet:
        select_query = """
                *,
                project_events(*),
                project_parties(*),
                project_deadlines(*),
                project_damages(*),
                project_claims(*),
                project_legal(*),
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
        if project_legal:
            project_legal.pop("created_at", None)
            project_legal.pop("project_id", None)
        else:
            logger.warning(f"No legal data found for project_id: {project_id}")

        factsheet = FactSheet(**data,
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
                project_attachments(*),
                project_events(*),
                project_parties(*),
                project_deadlines(*),
                project_damages(*),
                project_claims(*),
                project_legal(*),
                project_emails(*)"""
            
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
        if project_legal:
            project_legal.pop("created_at", None)
            project_legal.pop("project_id", None)
        else:
            logger.warning(f"No legal data found for project_id: {project_id}")

        factsheet = FactSheet(**data,
                              **project_legal,
                              parties=project_parties,
                              events=project_events,
                              deadlines=project_deadlines,
                              damages=project_damages,
                              claims=project_claims)
        attachments_models = [Attachment(**attachment) for attachment in attachments]
        emails_models = [Email(**email) for email in project_emails]
        return {
            "factsheet": factsheet,
            "attachments": attachments_models,
            "emails": emails_models,
        }

    def save_project(self,
                       factsheet : FactSheet,
                       files  : list[Attachment],
                       user_id : str,
                       project_id : str,
                       session_id : str,
                       query_id : str = "",
                       emails : list[Email] = []
                       ):
        
        custom_fields = ["governing_law", "disputed_facts", "undisputed_facts",]
        
        file_dicts = []
        email_dicts = []
        if files:
            for file in files:
                file_dict = file.model_dump(mode='json', exclude={"events","claims","damages","deadlines"})
                file_dict["project_id"] = project_id
                file_dicts.append(file_dict)
            logger.debug(f' ========= ATTACHEMNT CONTENTS TO SAVE ======== \n {files} \n')
        
        if emails:
            for email in emails:
                email_dict = email.model_dump(mode='json', exclude={"events","claims","damages","deadlines"})
                email_dict["project_id"] = project_id
                # Map from_addr to from for database compatibility
                if "from_addr" in email_dict:
                    email_dict["from"] = email_dict.pop("from_addr")
                email_dicts.append(email_dict)
        
        factsheet_dict = factsheet.model_dump(mode='json')
        claims = factsheet_dict.pop("claims", [])
        damages = factsheet_dict.pop("damages", [])
        deadlines = factsheet_dict.pop("deadlines", [])
        events = factsheet_dict.pop("events", [])
        parties = factsheet_dict.pop("parties", [])
        custom = {}
        for key in custom_fields:
            custom[key] = factsheet_dict.pop(key, None)
        
        factsheet_dict["project_id"] = project_id
        factsheet_dict["user_id"] = user_id
        factsheet_dict["updated_session_id"] = session_id
        factsheet_dict["updated_query_id"] = query_id
        factsheet_dict["updated_at"] = datetime.now().isoformat()
        # ========== PROJECT FACTSHEET ==========
        if factsheet_dict:
            try:
                self.supabase.table("projects").upsert(factsheet_dict).execute()
                logger.debug(f'Project {project_id} upserted in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting factsheet project {project_id} in Supabase: {e}. Stopping process.', exc_info=True)
                return
            if email_dicts:
                try:
                    # ========== PROJECT EMAILS ==========
                    self.supabase.table("project_emails").upsert(email_dicts).execute()
                    logger.debug(f'Upserted {len(emails)} emails for project {project_id} in Supabase.')
                except Exception as e:
                    logger.error(f'Error upserting emails for project {project_id} in Supabase: {e}', exc_info=True)

        if file_dicts:
            try:
                # ========== PROJECT ATTACHMENTS ==========
                self.supabase.table("project_attachments").upsert(file_dicts).execute()
                logger.debug(f'Upserted {len(files)} attachments for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting attachments for project {project_id} in Supabase: {e}', exc_info=True)

        if custom:
            #========= PROJECT CUSTOM FIELDS ==========
            try:
                self.supabase.table("project_legal").upsert({**custom, "project_id": project_id}).execute()
                logger.debug(f'Custom fields for project {project_id} upserted in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting custom fields for project {project_id} in Supabase: {e}', exc_info=True)

        if parties:
            # ========== PROJECT PARTIES ==========
            try:
                parties_with_project = [
                        {**party, "project_id": project_id}
                        for party in parties]
                self.supabase.table("project_parties").upsert(parties_with_project).execute()
                logger.debug(f'Upserted {len(parties)} parties for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting parties for project {project_id} in Supabase: {e}', exc_info=True)

        if events:
            # ========== PROJECT EVENTS ==========
            try:
                events_with_project = [
                        {**event, "project_id": project_id}
                        for event in events]
                self.supabase.table("project_events").upsert(events_with_project).execute()
                logger.debug(f'Upserted {len(events)} events for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting events for project {project_id} in Supabase: {e}', exc_info=True)

        if deadlines:
            # ========== PROJECT DEADLINES ==========
            try:
                deadlines_with_project = [
                        {**deadline, "project_id": project_id}
                        for deadline in deadlines]
                self.supabase.table("project_deadlines").upsert(deadlines_with_project).execute()
                logger.debug(f'Upserted {len(deadlines)} deadlines for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting deadlines for project {project_id} in Supabase: {e}', exc_info=True)

        # ========== PROJECT DAMAGES ==========
        if damages:
            try:
                damages_with_project = [
                        {**damage, "project_id": project_id}
                        for damage in damages]
                self.supabase.table("project_damages").upsert(damages_with_project).execute()
                logger.debug(f'Upserted {len(damages)} damages for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting damages for project {project_id} in Supabase: {e}', exc_info=True)

        if claims:
            # ========== PROJECT CLAIMS ==========
            try:
                claims_with_project = [
                        {**claim, "project_id": project_id}
                        for claim in claims]
                self.supabase.table("project_claims").upsert(claims_with_project).execute()
                logger.debug(f'Upserted {len(claims)} claims for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting claims for project {project_id} in Supabase: {e}', exc_info=True)
        
        logger.debug(f'Completed save_project for project {project_id}. Parties: {len(parties) if parties else 0}, Events: {len(events) if events else 0}, Deadlines: {len(deadlines) if deadlines else 0}, Damages: {len(damages) if damages else 0}, Claims: {len(claims) if claims else 0}')

    def insert_project_element(self,data : list[dict],
                    project_id : str,
                    table_name: str):
        if not data:
            logger.warning(f"No data provided to insert for project {project_id} in table {table_name}. Skipping insert.")
            return
        if not isinstance(data, list):
            raise ValueError("Data must be a list of BaseModel or dict instances.")
        
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item["project_id"] = project_id
        try:
            self.supabase.table(table_name).insert(data).execute()
            logger.debug(f'Inserted {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.error(f'Error inserting items for project {project_id} in Supabase table {table_name}: {e}',exc_info=True)
    
    def replace_project_element(self,
                    data : list[BaseModel],
                    project_id : str,
                    table_name: str):
        if not data:
            logger.warning(f"No data provided to replace for project {project_id} in table {table_name}. Skipping replace.")
            return

        data_dicts = []
        for item in data:
            item_dict = item.model_dump(mode='json') if hasattr(item, 'model_dump') else item
            if not isinstance(item_dict, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item_dict["project_id"] = project_id
            data_dicts.append(item_dict)

        try:
            self.supabase.table(table_name).delete().eq("project_id", project_id).execute()
            
            if data_dicts:  
                self.supabase.table(table_name).insert(data_dicts).execute()
            else:
                logger.warning(f"No data provided to replace for project {project_id} in table {table_name}. Skipping insert after delete.")
            
            logger.debug(f'Replaced {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.error(f'Error replacing items for project {project_id} in Supabase table {table_name}: {e}')

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
            sorted_sessions = sorted(
                project_sessions.data, 
                key=lambda x: x.get("updated_at") or "", 
                reverse=True
            )
            return sorted_sessions
        return []

    def load_user_sessions(self, user_id: str)-> list:
        '''Load all sessions for a user from Supabase'''
        try:
            sessions = self.supabase.table("sessions").select("title, session_id, updated_at").eq("user_id", user_id).order("updated_at", desc=True).execute()
            if sessions.data:
                sorted_sessions = sorted(
                sessions.data, 
                key=lambda x: x.get("updated_at") or "", 
                reverse=True
            )
            logger.debug(f'Loaded {len(sessions.data)} sessions for user {user_id} from Supabase.')
            return sorted_sessions
            
        except Exception as e:
            logger.error(f'Could not load sessions for user {user_id} from Supabase: {e}', exc_info=True)
            return []

    def load_session_history(self, session_id: str,
                             #user_id: str = None
                             ) -> dict: #rm user_id
        '''Load session history for a given session from Supabase'''
        query = """ *,
                    session_events(*),
                    session_attachments(*)
                    """
        response = self.supabase.table("sessions").select(query).eq("session_id", session_id).single().execute()
        if response.data:
            session_data = response.data
            session_events = session_data.pop("session_events", [])
            session_attachments = session_data.pop("session_attachments", [])
            logger.debug(f'Loaded session history for session {session_id} from Supabase.')
            return {
                    "events": session_events,  
                    'attachments': session_attachments,
                    "project_id": session_data.get("project_id",""),
                    "title": session_data.get("title",""), 
                    "llm_model": session_data.get("llm_model"),
                    "updated_at": session_data.get("updated_at"),
                }
        else:
            logger.warning(f"No session found for session_id: {session_id} in Supabase.")
            return {
                    "events": [],
                    'attachments': [],
                    "project_id": "",
                    "title": "Ny samtale", 
                    "llm_model": None,
                    "updated_at": None,
                }

    def save_stream(self, 
                    data : StreamData,
                    user_id : str,
                    session_id : str): 
        # Implement saving stream to Supabase
        new_events = [] 
        new_attachments = [] 
        for event in data.events:
            event_dict = event.model_dump(mode = "json")
            event_dict["session_id"] = session_id
            new_events.append(event_dict)
        for attachment in data.attachments:
            attachment_dict = attachment.model_dump(mode = "json")
            attachment_dict["session_id"] = session_id
            attachment_dict.pop("content", None)  # Remove content if present before saving
            new_attachments.append(attachment_dict)

        result = (
            self.supabase
            .table("sessions")
            .select("title")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )

        title = result.data[0]["title"] if result.data else None

        if not title or title == "Ny samtale":
            try:
                title_msg = [msg.get("content") for msg in new_events if msg.get("type") == "human" or msg.get("type") == "ai"]
                #title = await self.mk_title(title_msg)
                summarizer = Summarizer()
                title = summarizer.mk_title(title_msg)
            except Exception as e:
                logger.error(f"Error creating title: {e}", exc_info=True)
                title = "Ny samtale"

        try:
            self.supabase.table("sessions").upsert({
                "session_id": session_id,
                "user_id": user_id,
                "title" : title,
                "project_id": data.project_id,
                "llm_model" : data.llm_model,}).execute()
            logger.debug(f'Session {session_id} upserted in Supabase.')
        except Exception as e:
            logger.error(f'Error upserting session {session_id} in Supabase: {e}. Stopping process.', exc_info=True)
            return 

        try:
            self.supabase.table("session_events").insert(new_events).execute() if new_events else None
            logger.debug(f'Inserted {len(new_events)} events for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting events for session {session_id} in Supabase: {e}', exc_info=True)
        try:
            self.supabase.table("session_attachments").insert(new_attachments).execute() if new_attachments else None
            logger.debug(f'Inserted {len(new_attachments)} attachments for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting attachments for session {session_id} in Supabase: {e}', exc_info=True)



class EmailParser:
    def __init__(self):
        pass

    def _dedoce_base64(self, content: str) -> bytes:
        try:
            return base64.b64decode(content)
        except Exception as e:
            logger.error(f"Error decoding base64 content: {e}", exc_info=True)
            raise ValueError("Invalid base64 content") from e

    def _extract_email_body(self, msg : Message) -> dict:
        if msg.is_multipart():
            body_text = ""
            body_html = None
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body_text += part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
                elif content_type == "text/html":
                    body_html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")
        else:
            body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8")
            body_html = None
        return {"html" : body_html, "text": body_text}

    def _extract_attachments(self, msg : Message) -> list:
        allowed_types = ["application/pdf", 
                         "application/msword", 
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                         "text/plain",
                         "text/csv",
                         "message/rfc822",

                         ]
        attachments = []
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition")
            if content_disposition and "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    if part.get_content_type() in allowed_types:
                        payload = part.get_payload(decode=True)
                        try:
                            content = payload.decode(part.get_content_charset() or "utf-8")
                        except (UnicodeDecodeError, LookupError):
                            content = base64.b64encode(payload).decode("ascii")
                        attachments.append({
                            "filename": filename,
                            "file_type": part.get_content_type(),
                            "size" : len(payload),
                            "file_id": str(uuid.uuid4()),
                            "content": content
                        })
                    else:
                        logger.warning(f"Attachment '{filename}' has unsupported content type '{part.get_content_type()}', skipping. Allowed types are: {allowed_types}")
                else:
                    logger.warning("Attachment part found without filename, skipping.")
        return attachments
 
    def _extract_email_data(self, msg : Message, file_id : str, query_id : str, user_id: str , session_id : str) -> dict:
        #file_id = str(uuid.uuid4())
        attachments_list = self._extract_attachments(msg)
        attachments = []
        att_ids = []
        if attachments_list:
            for att in attachments_list:
                ext = os.path.splitext(att["filename"])[1].lower()
                attachment_model = AttachmentModel(
                    filename=att["filename"],
                    file_id=att["file_id"],
                    file_type=att["file_type"],
                    size=att["size"],
                    content=att["content"],
                    query_id=query_id,
                    event_id=None,
                    path = f'{user_id}/{session_id}/{att.get("file_id")}{ext}',
                )
                attachments.append(attachment_model)
                att_ids.append(att["file_id"])
        body = self._extract_email_body(msg)
        refs = msg.get("References")
        email_data = EmailModel(
                file_id=file_id,
                path = f'{user_id}/{session_id}/{file_id}.eml',
                query_id=query_id,

                subject=msg.get("Subject", ""),
                from_addr=msg.get("From", ""),
                to=[addr.strip() for addr in msg.get("To", "").split(",")],
                cc=[addr.strip() for addr in msg.get("Cc", "").split(",")] if msg.get("Cc") else None,
                bcc=[addr.strip() for addr in msg.get("Bcc", "").split(",")] if msg.get("Bcc") else None,
                date=email.utils.parsedate_to_datetime(msg.get("Date")) if msg.get("Date") else None,

                message_id=msg.get("Message-ID"),
                in_reply_to=msg.get("In-Reply-To"),
                references=refs,
                thread_id=msg.get("Thread-ID"),
                thread_index=msg.get("Thread-Index"),
                thread_topic=msg.get("Thread-Topic"),

                body_text=body.get("text", ""),
                body_html=body.get("html"),
                headers=dict(msg.items()) if msg.items() else None,

                attachments=att_ids if att_ids else None,
            )

        return {"email" : email_data, "attachments" : attachments if attachments else []}

    def parse_eml(self, content: str, user_id, query_id, session_id, file_id) -> dict:
        '''Process EML content and extract email data and attachments
        
        Args:
            content (str): The EML content as a base64 encoded string.
            user_id (str): The ID of the user associated with the email.
            query_id (str): The ID of the query associated with the email.
            session_id (str): The ID of the session associated with the email.
            file_id (str): The ID of the file associated with the email.
        Returns:
            dict: A dictionary containing the extracted email data and attachments.
        
        '''
        content = self._dedoce_base64(content)
        try:
            msg = email.message_from_bytes(content)
        except Exception as e:
            logger.error(f"Error parsing EML content: {e}", exc_info=True)
            raise ValueError("Invalid EML content") from e
        email_data = self._extract_email_data(msg, 
                                              query_id=query_id, 
                                              user_id=user_id, 
                                              session_id=session_id, 
                                              file_id=file_id)
        return email_data
    
