import os
import logging
from fastapi import HTTPException
from google.cloud import firestore

from models import *
from agent.agent_modules import Summarizer


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
            logger.error(f'❌ Could not load projects for user {user_id}: {e}', exc_info=True)
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
            logger.error(f'❌ Could not load sessions for user {user_id}: {e}', exc_info=True)
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
            logger.error(f'❌ Could not load sessions for user {user_id}: {e}', exc_info=True)
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
            logger.error(f"❌ Error saving final state: {e}", exc_info=True)
    
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
            logger.error(f"❌ Error saving project to Firestore: {e}", exc_info=True)

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

