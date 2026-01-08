import json
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

from langchain_openai import ChatOpenAI
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore

from google.cloud import bigquery
from google.cloud import storage
from google.cloud import bigquery
from google.cloud import firestore





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
    def __init__(self, dataset: str = "vector_store", region: str = "europe-west1",model_name: str = "text-embedding-005"):
        self.dataset = dataset
        self.region = region
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.embedding = GoogleGenerativeAIEmbeddings(model_name=model_name)

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
        #print(f"TEXT TO PARSE: {txt_content[:500]}...")
        splitter = RecursiveCharacterTextSplitter(chunk_size = 1000, chunk_overlap=200)
        texts = splitter.split_text(txt_content)
        docs = []
        for t in texts:
            doc = Document(
                page_content=t,
                metadata=metadata
            )
            docs.append(doc)
        return docs
    
    def query(self, query : str, table_name : str, filters : dict) -> list[Document]:
        vector_store = self.init_vector_store(table_name)
        retriever = vector_store.as_retriever(search_kwargs={"k": 3})
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
        self.domain = "company"
        
    def save_stream(self, 
                    events : list, 
                    attachments : list,
                    user_id : str, 
                    session_id : str, 
                    agent_type : Literal["fast", "expert"] = "fast", 
                    llm_provider : Literal["google", "openai", "claude"] = "google", 
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
                "agent_type": agent_type,
                "llm_provider": llm_provider,
                "last_query_id": query_id,
                "title" : title
            })
            
            logger.info(f"Session saved with {len(all_events)} total events")
        except Exception as e:
            logger.error(f"Error saving final state: {e}", exc_info=True)
    
class ContextManager:
    def __init__(self):
        pass

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

