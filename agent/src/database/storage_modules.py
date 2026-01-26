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

from agent.basemodels import *
from supabase import create_client, Client
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


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

class GCSManager:

    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", "chat-history-files")
        self.bucket = self.client.bucket(self.bucket_name)
    
    async def save_attachment(self,content : bytes, path : str):
        try:
            blob = self.bucket.blob(path)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, blob.upload_from_string, content)
            logger.info(f"Attachment saved to GCS at {path}")
        except Exception as e:
            logger.error(f"Error saving attachment to GCS: {e}")

    async def save_raw_documents(self, attachments: list[AttachmentModel], bucket_name: str = "session_attachments"):
        """Lagrer alle vedlegg parallelt"""
        tasks = []
        
        for att in attachments:
            # meta = {
            #     "filename": att.filename,
            #     "file_id": att.file_id,
            #     "user_id": user_id,
            #     "session_id": session_id,
            #     'query_id': query_id,
            #     "source_type": att.file_type,
            #     "uploaded_at": datetime.now().isoformat(),
            # }
            content = att.content
            
            # Decode content
            if att.file_type == "application/pdf":
                content_bytes = base64.b64decode(content)
                tasks.append(self.save_attachment(content_bytes, path=att.path, bucket_name=bucket_name))
            else:
                tasks.append(self.save_attachment(content, path=att.path, bucket_name=bucket_name))
        
        # Kjør alle uploads parallelt
        await asyncio.gather(*tasks)

class SupabaseStorageManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)

    def save_attachment(self, content: bytes, path : str, bucket_name: str = "session_attachments"):
        try:
            self.supabase.storage.from_(bucket_name)\
                .upload(file = content, 
                        path = path, 
                        file_options={"cache-control" : "3600"})
            logger.info(f"Attachment saved to Supabase Storage at {path}")
        except Exception as e:
            logger.error(f"Error saving attachment to Supabase Storage: {e}")
            

    async def save_raw_documents(self, attachments: list[AttachmentModel]):
        for att in attachments:
            path = att.path
            content = att.content
            if att.file_type == "application/pdf":
                content_bytes = base64.b64decode(content)
                self.save_attachment(content=content_bytes, path=path)
            else:
                self.save_attachment(content=content, path=path)
        logger.info(f"All attachments saved to Supabase Storage.")
    
    def read_attachment(self, path : str, bucket_name: str = "session_attachments") -> bytes:
        response = self.supabase.storage.from_(bucket_name)\
            .download(path)
        return response
