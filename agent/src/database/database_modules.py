
import asyncio
import token
from typing import Optional, Literal
import os
from io import BytesIO
from PyPDF2 import PdfReader
import logging
import base64

from langchain_core.messages import SystemMessage
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore


from google.cloud import bigquery
from google.cloud import storage
from google.cloud import bigquery
from google.cloud import firestore

from agent.basemodels import *
from fastapi import FastAPI,HTTPException,status,Depends
from agent.agent_modules import Summarizer
#from ui.ui_components import attachments
from supabase import create_client, Client
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


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
            logger.error(f'Could not load projects for user {user_id}: {e}')
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
            logger.error(f'Could not load sessions for user {user_id}: {e}')
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
            logger.error(f"Error loading session history: {e}")
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
            logger.error(f'Could not load sessions for user {user_id}: {e}')
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
                    title_msg = [msg.get("data") for msg in new_events if msg.get("type") == "human" or msg.get("type") == "ai"]
                    #title = await self.mk_title(title_msg)
                    title = self.summarizer.mk_title(title_msg)
                except Exception as e:
                    logger.error(f"Error creating title: {e}")
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
                       llm_model : str,
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
                "last_updated_session_id": session_id,
                "last_updated_query_id": query_id,
                "created_at": firestore.SERVER_TIMESTAMP,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "llm_model": llm_model,
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

    def load_project(self, user_id: str, project_id: str):
        # Implement loading project from Supabase
        return

    def save_project(self,
                       factsheet : FactSheet,
                       files  : list[Attachment],
                       user_id : str,
                       project_id : str,
                       session_id : str,
                       llm_model : str,
                       query_id : str = ""
                       ):
        # Implement saving project to Supabase
        pass

    def load_projects(self,user_id: str):
        # Implement loading projects from Supabase
        pass

    def load_project_sessions(self, user_id: str, project_id: str):
        # Implement loading project sessions from Supabase
        pass

    def get_or_create_user(self, google_user_info: dict) -> str:
        # Implement user retrieval/creation in Supabase
        pass

    def load_user_sessions(self, user_id: str)-> list:
        '''Load all sessions for a user from Supabase'''
        # Implement loading user sessions from Supabase
        try:
            sessions = self.supabase.table("sessions").select("title, session_id, updated_at").eq("user_id", user_id).execute()
            logger.debug(f'Loaded {len(sessions.data)} sessions for user {user_id} from Supabase.')
            return sessions.data
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
        return {
                "events": session_events.data,  
                'attachments': session_attachments.data,
                "project_id": session_data.get("project_id",""),
                "title": session_data.get("title",""), 
                "llm_model": session_data.get("llm_model"),
                "last_updated": session_data.get("updated_at"),
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

        title = self.supabase.table("sessions").select("title").eq("session_id", session_id).execute().data
        if not title:
            try:
                title_msg = [msg.get("data") for msg in new_events if msg.get("type") == "human" or msg.get("type") == "ai"]
                #title = await self.mk_title(title_msg)
                summarizer = Summarizer()
                title = summarizer.mk_title(title_msg)
            except Exception as e:
                logger.error(f"Error creating title: {e}")
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
            logger.error(f'Error upserting session {session_id} in Supabase: {e}. Stopping process.')
            return 

        try:
            self.supabase.table("session_events").insert(new_events).execute() if new_events else None
            logger.debug(f'Inserted {len(new_events)} events for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting events for session {session_id} in Supabase: {e}')
        try:
            self.supabase.table("session_attachments").insert(new_attachments).execute() if new_attachments else None
            logger.debug(f'Inserted {len(new_attachments)} attachments for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting attachments for session {session_id} in Supabase: {e}')
