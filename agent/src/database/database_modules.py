
from typing import Optional, Literal
import os
from io import BytesIO
from PyPDF2 import PdfReader
import logging

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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorSearch:
    def __init__(self, dataset: str = "vector_store", region: str = "europe-north2",model_name: str = "text-embedding-004"):
        self.dataset = dataset
        self.region = region
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.embedding = GoogleGenerativeAIEmbeddings(model=model_name)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap=200)

    def init_vector_store(self, table_name : str) -> BigQueryVectorStore:
        PROJECT_ID = self.project_id
        REGION = self.region
        DATASET = self.dataset
        TABLE = table_name

        vector_store = BigQueryVectorStore(
            project_id=PROJECT_ID,
            dataset_name=DATASET,
            table_name=TABLE,
            location=REGION,
            embedding=self.embedding,
        )
        return vector_store

    def parse_pdf(self, content_bytes: bytes, metadata : dict) -> list[Document]:
        reader = PdfReader(BytesIO(content_bytes))
        docs = []
        metadata_base = metadata
        for i, page in enumerate(reader.pages):
            doc = Document(
                page_content=page.extract_text(),
            metadata={
                #"source": source,
                "page": i + 1,
                "total_pages": len(reader.pages),
                "creator": reader.metadata.get("/Creator"),
                "producer": reader.metadata.get("/Producer"),
                **metadata_base
                }
            )
            docs.append(doc)
        return docs

    def parse_txt(self, txt_content: str, metadata : dict) -> list[Document]:
        texts = self.splitter.split_text(txt_content)
        docs = []
        for i, page in enumerate(texts):
            doc_meta = metadata | {
                "page": i + 1,
                "total_pages": len(texts),
            }
            doc = Document(
                page_content=page,
                metadata=doc_meta
            )
            docs.append(doc)
        return docs
    
    
    def query(self, query : str, table_name : str,n_results = 3) -> list[Document]:
        vector_store = self.init_vector_store(table_name)
        retriever = vector_store.as_retriever(search_kwargs={"k": n_results})
        results = retriever.invoke(query)
        return [doc.model_dump_json() for doc in results]

    def retrieve_relevant_attachments(self,query_id, query, n_docs = 4) -> SystemMessage:
        vs_attachments = self.init_vector_store(table_name="attachments")

        try:
            retriever = vs_attachments.as_retriever(search_kwargs={"k": n_docs ,"filter" : 
                                                     {"query_id" :  query_id} })
            relevant_docs = retriever.invoke(query)
            relevant_texts = "\n\n".join([f"[{doc.metadata.get('type')}]: {doc.page_content}" for doc in relevant_docs])  # Behold type for kontekst
            logger.info(f'Found {len(relevant_docs)} relevant documents from BQ vector store.')
            return relevant_texts

        except Exception as e:
            logger.error(f'Error downloading attachments from GCS: {e}')
            return   # Return empty summary on error
       
    def retrieve_txt_content(self, table : str, conditions : dict):
        '''
        Read content from BigQuery table with optional conditions.
        
        Args:
            table (str): The name of the BigQuery table.
            conditions (dict): A dictionary of conditions to filter the query.  

        Returns:
            list[str]: A list of content strings from the query results.
        '''
        client = bigquery.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"))
        table_id = f"{os.getenv('GOOGLE_CLOUD_PROJECT')}.vector_store.{table}"
        

        query = f"SELECT content FROM `{table_id}`"

        conditions_list = []
        for k,v in conditions.items():
            if v is not None:
                conditions_list.append(f"{k} = '{v}'")

        if conditions_list:
            query += " WHERE " + " AND ".join(conditions_list)
        result = client.query(query).result()
        return [row["content"] for row in result]
        
class AttachmentReader:

    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "chat-history-files")
        self.bucket = self.client.bucket(self.bucket_name)
    
    def _extract_text(self, blob, type : str) -> str:
        if type == "application/pdf":
            content = blob.download_as_bytes()
            reader = PdfReader(BytesIO(content))
            content = ""
            for page in reader.pages:
                content += page.extract_text()
        else:
            content = blob.download_as_text()
        return content
    
    def read_attachment(self, session_id : str, user_id : str, file_id : str, file_type : str) -> str:
        try:
            blob = self.bucket.blob(f"{user_id}/{session_id}/{file_id}")
            txt += self._extract_text(blob, file_type) + "\n\n"
            logger.info(f'Downloaded attachment content from GCS for {blob.name}')
            return txt
        except Exception as e:
            logger.error(f'Error downloading attachments from GCS: {e}')
            return f"Error downloading attachments from GCS: {e}"
        
    def save_attachment(self,content : bytes,metadata : dict = None):
        file_id = metadata.pop("file_id",None)
        session_id = metadata.pop("session_id",None)
        user_id = metadata.pop("user_id",None)
        if not file_id or not session_id or not user_id:
            logger.error(f"Missing file_id, session_id or user_id in metadata. Cannot save attachment.")
            return
        
        try:
            bucket_path = f"{user_id}/{session_id}/{file_id}"
            blob = self.bucket.blob(bucket_path)
            blob.metadata = metadata
            blob.upload_from_string(content)
            logger.info(f"Attachment saved to GCS at {bucket_path}")
        except Exception as e:
            logger.error(f"Error saving attachment to GCS: {e}")

class ConversationManager:
    def __init__(self, db=None):
        self.db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT"), database="(default)") if not db else db
        self.summarizer = Summarizer()
        
    def load_project(self, user_id: str, project_id: str):
        try:
            factsheet_ref = (
                self.db.collection("projects")
                .document(user_id)
                .collection("factsheets")
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
                .collection("factsheets")
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
                    "agent_type": session_data.get("agent_type"),
                    "llm_provider": session_data.get("llm_provider"),
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
                "agent_type": session_data.get("agent_type"),
                "llm_provider": session_data.get("llm_provider"),
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
                    "agent_type": session_data.get("agent_type"),
                    "llm_provider": session_data.get("llm_provider"),
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
                    events : list, 
                    attachments : list,
                    user_id : str, 
                    session_id : str, 
                    agent_type : Literal["fast", "expert"] = "fast", 
                    llm_provider : Literal["google", "openai", "claude"] = "google", 
                    project_id : Optional[str] = None,
                    query_id : str = ""): 
        ''' Save the final state of the conversation session to Firestore 
        
        Args:
            events (list): List of event dicts to save.
            attachments (list): List of attachment dicts to save.
            user_id (str): User identifier.
            session_id (str): Session identifier.
            agent_type (str): Type of agent used.
            llm_provider (str): LLM provider used.
            query_id (str): Query identifier.

        Returns:
            None
        '''
        
        
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
                    title_msg = [msg.get("data") for msg in events if msg.get("type") == "human" or msg.get("type") == "ai"]
                    #title = await self.mk_title(title_msg)
                    title = self.summarizer.mk_title(title_msg)
                except Exception as e:
                    logger.error(f"Error creating title: {e}")
                    title = "Ny samtale"

            all_events.extend(events) if events else None
            all_attachments.extend(attachments) if attachments else None

             # Save updated session
            session_ref.set({
                "events": all_events, 
                "attachments": all_attachments,
                "last_updated": firestore.SERVER_TIMESTAMP,
                "project_id": project_id,
                "agent_type": agent_type,
                "llm_provider": llm_provider,
                "last_query_id": query_id,
                "title" : title
            })
            
            logger.info(f"Session saved with {len(all_events)} total events")
        except Exception as e:
            logger.error(f"Error saving final state: {e}", exc_info=True)
    
    def save_init_scan(self,
                       factsheet : FactSheet,
                       files  : list[Attachment],
                       user_id : str,
                       project_id : str,
                       session_id : str,
                       agent_type : Literal["fast", "expert"] = "fast",
                       llm_provider : Literal["google", "openai", "claude"] = "google",
                       query_id : str = ""

                       ):
        ''' Save the initial case scan to Firestore
        
        Args:
            factsheet (FactSheet): The factsheet object to save.
            files (list): List of attachment objects to save.

        Returns:
            None
        '''

        ref = self.db.collection("projects").document(user_id).collection("factsheets").document(project_id)
        try:
            ref.set({
                "user_id": user_id,
                "created_session_id": session_id,
                "created_query_id": query_id,
                "created_at": firestore.SERVER_TIMESTAMP,
                "agent_type": agent_type,
                "llm_provider": llm_provider,
                "factsheet": factsheet.model_dump(mode='json'),
                "attachments": [file.model_dump(mode='json') for file in files]
            })
            logger.info(f"Initial case scan saved for project {project_id}")
        except Exception as e:
            logger.error(f"Error saving initial case scan: {e}", exc_info=True)

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
