import json
from pyexpat import model
from typing import Dict,TypedDict,List,Union,Annotated,Sequence,Optional, Literal, Tuple, Any
import os
from io import BytesIO
from PyPDF2 import PdfReader
import tiktoken
import logging

from langchain_core.messages import HumanMessage,AIMessage,SystemMessage,BaseMessage,ToolMessage,AIMessageChunk
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.language_models.chat_models import BaseChatModel


from langchain_openai import ChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore


from google.cloud import bigquery
from google.cloud import storage
from google.cloud import bigquery
from google.cloud import firestore

from agent.basemodels import *

logger = logging.getLogger(__name__)

class Summarizer:
    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.model = ChatOpenAI(model=model_name, temperature=0)

    def summarize(self, content: str, limit: int = None) -> str:
        if limit and len(content) > limit:
            logger.info(f'Tool result exceeded token limit of {limit}. Truncating result.')
            query  = f'Summarize the this data in 200-400 tokens: {str(content)[:limit//2]}... {str(content)[-limit//2:]}'
        else:
            query  = f'Summarize the this data in MAX 200-400 tokens: {str(content)}'
        summary_response = self.model.invoke(query)
        return summary_response.content if hasattr(summary_response, 'content') else str(summary_response)

    def mk_title(self, messages : list):
        prompt = f'Make a short title (2-5 words) as summary of this chat. MAX 5 words. Use company if present: {messages}'
        res = self.model.invoke(prompt)
        title = res.content
        logger.info(f'Generated title: {title}')
        return title

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
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "chat-history-attachments")
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
        self.domain = "legal"
        
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
                "domain": self.domain,
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
                "factsheet": factsheet.model_dump(),
                "attachments": [file.model_dump() for file in files]
            })
            logger.info(f"Initial case scan saved for project {project_id}")
        except Exception as e:
            logger.error(f"Error saving initial case scan: {e}", exc_info=True)

class ContextManager:
    def __init__(self, llm: BaseChatModel,
                 ):
        self.llm = llm
        #self.vector_search = VectorSearch()

    # ===== TRUNCATION HELPERS =====
    def truncate_tokens(self, messages, max_tokens=7000):
        """Truncate messages to fit within max_tokens while preserving tool-call structure."""
        enc = tiktoken.encoding_for_model("gpt-4o-mini")
        token_count = 0
        truncated = []

        for msg in reversed(messages):
            token_count += len(enc.encode(msg.content or ""))
            truncated.insert(0, msg)

            if token_count > max_tokens:
                break

        # Safety check: drop any orphan tool messages at the start
        while truncated and isinstance(truncated[0], ToolMessage):
            truncated.pop(0)

        # Safety check: drop trailing AIMessage with tool_calls if no following ToolMessages
        # This prevents OpenAI API error about missing tool responses
        if truncated and isinstance(truncated[-1], AIMessage) and hasattr(truncated[-1], 'tool_calls') and truncated[-1].tool_calls:
            logger.warning("Dropping trailing AIMessage with tool_calls after truncation to avoid API error")
            truncated.pop()

        return truncated

    def truncate_messages(self, messages, max_messages=20):
        """Truncate messages while preserving tool-call structure."""
        if len(messages) <= max_messages:
            return messages
        
        truncated = messages[-max_messages:]
        
        # Remove orphan tool messages at start
        while truncated and isinstance(truncated[0], ToolMessage):
            truncated.pop(0)
        
        # Remove trailing AIMessage with tool_calls if no ToolMessage follows
        if (truncated and 
            isinstance(truncated[-1], AIMessage) and 
            hasattr(truncated[-1], 'tool_calls') and 
            truncated[-1].tool_calls):
            logger.warning("Dropping trailing AIMessage with tool_calls to avoid API error")
            truncated.pop()
        
        return truncated

    # ===== FUNCTIONS FOR INITIAL FACTSHEET CREATION =====
    def analyze_init_input(self, init_input : str) -> InitialInput:
        structured_llm = self.llm.with_structured_output(InitialInput)
        prompt = f'Analyze the following case introduction and extract key information into the InitialInput structure:\n\n{init_input}'
        return structured_llm.invoke(prompt)
    
    def analyze_events(self, initial_input : InitialInput , content : str,file_id: str) -> list[Event]:
        '''Analyzes document content to extract a list of events.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            content (str): The document content to analyze.

        Returns:
            list[Event]: A list of extracted Event objects.
        '''
        structured_llm = self.llm.with_structured_output(List[Event])
        init_prompt = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key main events:\n\n{content}'
        response = structured_llm.invoke(prompt)
        for event in response:
            event.file_id = file_id
        return response
    
    def analyze_doc(self, 
                    initial_input : InitialInput ,
                    content: str, 
                    file_id : str, 
                    filename: str, 
                    path: str, 
                    file_type: str, 
                    size: int, 
                    ) -> dict:
        ''' Function to analyze document content and extract structured data as Attachment.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            content (str): The document content to analyze.
            file_id (str): The unique identifier for the file.
            filename (str): The name of the file.
            path (str): The storage path of the file.
            file_type (str): The MIME type of the file.
            size (int): The size of the file in bytes.
            query_id (str): The query identifier.   
            
            Returns:    
            Attachment: The structured Attachment object with extracted data.
        '''
        structured_llm = self.llm.with_structured_output(AttachmentExtracted)
        init_prompt = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key information into the Attachment structure:\n\n{content}'
        events = self.analyze_events(initial_input=initial_input, 
                                     content = content, 
                                     file_id = file_id)
        response = structured_llm.invoke(prompt)
        file = Attachment(**response.model_dump(),
                            file_id=file_id,
                            filename=filename,
                            path=path,
                            file_type=file_type,
                            size=size,
                            event_ids=[event.event_id for event in events],
                        )
        return {"file": file, "events": events}
    
    def analyze_governing_law(self, events : list[Event],rag_content_law : str) -> GoverningLaw:
        '''Function to analyze case events and extract governing law information.
        
        Args:
            events (list[Event]): The list of case events.
            rag_content_law (str): Relevant legal context retrieved via RAG.
            
        Returns:
            GoverningLaw : The structured GoverningLaw object with extracted information.
        '''
        structured_llm = self.llm.with_structured_output(GoverningLaw)
        law_context = f'Extracted legal context:\n\n{rag_content_law}\n\n' if rag_content_law else ''
        prompt = law_context + f'Based on the following case events, analyze and extract governing law information:\n\n{events}'
        return structured_llm.invoke(prompt)
        
    def analyze_factual_facts(self, 
                              initial_input : InitialInput, 
                              events : list[Event], 
                              #claims : list[Claim], 
                              #damages: list[Damage]
                              ) -> FactualFacts:
        '''Function to analyze case events and extract disputed and undisputed facts.
        
        Args:
            initial_input (InitialInput): The initial case input data.
            events (list[Event]): The list of case events.
        
        Returns: 
            FactualFacts : The structured FactualFacts object with disputed and undisputed facts.
        '''
        structured_llm = self.llm.with_structured_output(FactualFacts)
        init = f'Initial case input: {initial_input.model_dump()}\n\n'
        prompt = init + f'Based on the following case events, extract disputed and undisputed facts:\n\n{events}'
        return structured_llm.invoke(prompt)
    
    # ===== FUNCTIONS FOR UPDATING EXISTING FACTSHEET =====
    def consider_new_events(self,
                            factsheet : FactSheet,
                         new_content : str,
                         new_user_input : str,
                         file_id : str
                         ) -> list[Event]:
        structured_llm = self.llm.with_structured_output(List[Event])
        init_prompt = f'Existing factsheet:\n\n{factsheet.model_dump()}\n\n'
        prompt = init_prompt + f'Analyze the following document content and extract key main events:\n\n{new_content}' + f'\n\nNew user input:\n\n{new_user_input}\n\n'
        response = structured_llm.invoke(prompt)
        for event in response:
            event.file_id = file_id
        return response
    
    def consider_new_doc(self,
                            factsheet : FactSheet,
                         new_content : str,
                         new_user_input : str,
                         file_id : str,
                         filename : str,
                         path : str,
                         file_type : str,
                         size : int,
                         ) -> dict:
        '''Function to analyze new document content in relation to existing FactSheet.
        Args:
            factsheet (FactSheet): The existing FactSheet object.
            content (str): The new document content to analyze.
            file_id (str): The unique identifier for the file.
            filename (str): The name of the file.
            path (str): The storage path of the file.
            file_type (str): The MIME type of the file.
            size (int): The size of the file in bytes.

        Returns:
            dict: A dictionary indicating relevance and suggested updates.
        '''
        prompt = f'Existing factsheet:\n\n{factsheet.model_dump()}\n\n'
        prompt += f'Analyze the following document content and extract key information into the Attachment structure:\n\n{new_content}' + f'\n\nNew user input:\n\n{new_user_input}\n\n'

        structured_llm = self.llm.with_structured_output(AttachmentExtracted)
        response = structured_llm.invoke(prompt)
        events = self.consider_new_events(factsheet, new_content, new_user_input, file_id)
        file = Attachment(**response.model_dump(),
                            file_id=file_id,
                            filename=filename,
                            path=path,
                            file_type=file_type,
                            size=size,
                            event_ids=[event.event_id for event in events],
                        )
        return {"file": file, "events": events}

    def update_factsheet(self,
                         factsheet : FactSheet,
                         new_user_input : str,
                         new_content : Optional[str] = "",
                         file_id : Optional[str] = None,
                         filename : Optional[str] = None,
                         path : Optional[str] = None,
                         file_type : Optional[str] = None,
                         size : Optional[int] = None,
                         
                         ) -> FactSheet:
        '''Function to update an existing FactSheet with new input data.
        
        Args:
            factsheet (FactSheet): The existing FactSheet to update.
            new_user_input (str): The new input query or information from the user.
            new_content (str, optional): New document content to consider for updating the factsheet.
            file_id (str, optional): The unique identifier for the new document.
            filename (str, optional): The name of the new document.
            path (str, optional): The storage path of the new document.
            file_type (str, optional): The MIME type of the new document.
            size (int, optional): The size of the new document in bytes.
        
        Returns:
            FactSheet: The updated FactSheet object.
        '''
        existing_facts = f"Existing factsheet:\n\n{factsheet.model_dump()}"
        prompt = existing_facts + f'Return True if the following new input is relevant to update the existing factsheet, else return False:\n\n{new_user_input}'
        structured_llm = self.llm.with_structured_output(RelevanceCheck)  
        relevant = structured_llm.invoke(prompt)
        if relevant.is_relevant:
            result = self.consider_new_doc(new_content=new_content,
                                           new_user_input=new_user_input,
                                           factsheet=factsheet,
                                           file_id=file_id,
                                           filename=filename,
                                           path=path,
                                           file_type=file_type,
                                           size=size,)
            return result

            
        
class ToolManager:
    def __init__(self):
        pass

    def format_tool_result(self, result: Any) -> str:
        if isinstance(result, (dict, list)):
            try:
                return json.dumps(result, ensure_ascii=False)
            except (TypeError, ValueError):
                pass
        return str(result)


