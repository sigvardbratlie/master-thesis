
import asyncio
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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VectorSearch:
    def __init__(self, dataset: str = "vector_store", region: str = "europe-north2",model_name: str = "text-embedding-004"):
        self.dataset = dataset
        self.region = region
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.embedding = GoogleGenerativeAIEmbeddings(model=model_name)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap=200)
        self.vector_store = None

    def init_vector_store(self, table_name : str) -> BigQueryVectorStore:
        if self.vector_store:
            return self.vector_store
        else:
        
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
            self.vector_store = vector_store
            return vector_store

    def parse_pdf(self, content_bytes: bytes, metadata : dict) -> list[Document]:
        reader = PdfReader(BytesIO(content_bytes))
        docs = []
        metadata_base = metadata | {"total_pages": len(reader.pages),
                                    "creator": reader.metadata.get("/Creator") if reader.metadata else None,
                                    "producer": reader.metadata.get("/Producer") if reader.metadata else None,}
        for i, page in enumerate(reader.pages):
            doc = Document(
                page_content=page.extract_text(),
            metadata={
                #"source": source,
                "page": i + 1,
                
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

    def retrieve_relevant_attachments(self,query_id, query, n_docs = 4, vector_store : BigQueryVectorStore = None) -> SystemMessage:
        vector_store = self.init_vector_store(table_name="attachments") if not vector_store else vector_store

        try:
            retriever = vector_store.as_retriever(search_kwargs={"k": n_docs ,"filter" : 
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
        
    def fetch_attachment_contents(self,
                                    attachments: list,
                                    user_input: str,
                                    session_id: str,
                                    query_id: str) -> dict[str, str]:
        """
        Fetches content for all attachments from vector store (single retrieval).

        Args:
            attachments: List of attachment metadata
            user_input: User's query for RAG retrieval
            session_id: Session ID
            query_id: Query ID

        Returns:
            Dict mapping file_id to content string
        """
        if not attachments:
            return {}

        contents = {}
        try:
            for att in attachments:
                file_id = att.get("file_id", "")

                if user_input:
                    content = self.retrieve_relevant_attachments(query=user_input, query_id=query_id)
                else:
                    content = self.retrieve_txt_content(
                        table="attachments",
                        conditions={"file_id": file_id, "session_id": session_id}
                    )
                    content = " ".join(content) if isinstance(content, list) else content

                contents[file_id] = content if content else ""

        except Exception as e:
            logger.error(f"Error fetching attachment contents: {e}", exc_info=True)

        return contents
    
    def embedded_upload(self,attachments : list[AttachmentModel],query_id : str, session_id : str, user_id : str):
        vector_store = self.init_vector_store(table_name="attachments")
        docs = []
        
        for att in attachments:
            meta = {
                "filename": att.filename,
                "file_id": att.file_id,
                "user_id": user_id,
                "session_id": session_id,
                'query_id': query_id,
                "source_type": att.file_type,  # 'application/pdf' eller 'text/plain'
                "uploaded_at": datetime.now().isoformat(),
            }
            content = att.content #b64 or human readable text

            #decode content
            if att.file_type == "application/pdf":
                content_bytes = base64.b64decode(content)
                docs.extend(self.parse_pdf(content_bytes, metadata=meta))
            else:
                docs.extend(self.parse_txt(content, metadata=meta))
        vector_store.add_documents(docs) # Save in vector store

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
        
    async def save_attachment(self,content : bytes,metadata : dict = None):
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
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.upload_from_string, content)
            logger.info(f"Attachment saved to GCS at {bucket_path}")
        except Exception as e:
            logger.error(f"Error saving attachment to GCS: {e}")

    async def save_raw_documents(self, attachments: list[AttachmentModel], query_id: str, session_id: str, user_id: str):
        """Lagrer alle vedlegg parallelt"""
        tasks = []
        
        for att in attachments:
            meta = {
                "filename": att.filename,
                "file_id": att.file_id,
                "user_id": user_id,
                "session_id": session_id,
                'query_id': query_id,
                "source_type": att.file_type,
                "uploaded_at": datetime.now().isoformat(),
            }
            
            content = att.content
            
            # Decode content
            if att.file_type == "application/pdf":
                content_bytes = base64.b64decode(content)
                tasks.append(self.save_attachment(content_bytes, metadata=meta))
            else:
                tasks.append(self.save_attachment(content, metadata=meta))
        
        # Kjør alle uploads parallelt
        await asyncio.gather(*tasks)

class ConversationManager:
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
            
            logger.info(f"Session saved with {len(all_events)} total events")
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
            logger.info(f"Project saved for project {project_id}")
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
        user_id = "53d63d18-cfa1-416e-96e8-770c8f66507b" #må fixes!!! kun pr nå for debugging!
        try:
            sessions = self.supabase.table("sessions").select("title, session_id, updated_at").eq("user_id", user_id).execute()
            logger.info(f'Loaded {len(sessions.data)} sessions for user {user_id} from Supabase.')
            return sessions.data
        except Exception as e:
            logger.error(f'Could not load sessions for user {user_id} from Supabase: {e}')
            return []

    def load_session_history(self, session_id: str, user_id: str = None)-> dict: #rm user_id
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
            logger.info(f'Loaded session history for session {session_id} from Supabase.')
        except Exception as e:
            logger.error(f'Could not load session for session {session_id} from Supabase: {e}')
            return {"error": str(e)}
        
        session_data = session.data[0] if session.data else {}
        return {
                "events": session_events.data,  
                'attachments': session_attachments.data,
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

        try:
            self.supabase.table("sessions").upsert({
                "session_id": session_id,
                "user_id": "53d63d18-cfa1-416e-96e8-770c8f66507b", #user_id, #må fixes!!! kun pr nå for debugging! 
                "title" : "",
                "project_id": data.project_id,
                "llm_model" : data.llm_model,}).execute()
            logger.info(f'Session {session_id} upserted in Supabase.')
        except Exception as e:
            logger.error(f'Error upserting session {session_id} in Supabase: {e}. Stopping process.')
            return 

        try:
            self.supabase.table("session_events").insert(new_events).execute() if new_events else None
            logger.info(f'Inserted {len(new_events)} events for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting events for session {session_id} in Supabase: {e}')
        try:
            self.supabase.table("session_attachments").insert(new_attachments).execute() if new_attachments else None
            logger.info(f'Inserted {len(new_attachments)} attachments for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting attachments for session {session_id} in Supabase: {e}')
