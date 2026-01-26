import os
from io import BytesIO
from PyPDF2 import PdfReader
import logging
import base64
from datetime import datetime

from langchain_core.messages import SystemMessage
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_chroma import Chroma

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore

from google.cloud import bigquery
from google.cloud import bigquery

from agent.basemodels import AttachmentModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from abc import ABC, abstractmethod
from typing import List, Dict, Optional

# ============================================
#           ABSTRACT BASE CLASS
# ============================================
class VectorStoreInterface(ABC):
    """Clean interface - ALL vector stores implement this."""
    
    @abstractmethod
    def add_documents(self, documents: List[Document]) -> None:
        """Add documents to store."""
        pass
    
    @abstractmethod
    def query(self, query: str, filters: Dict = None, k: int = 3) -> List[Document]:
        """Query documents."""
        pass
    
    @abstractmethod
    def delete_collection(self, collection_id: str) -> None:
        """Delete collection."""
        pass


# ============================================
#           CHROMA IMPLEMENTATION
# ============================================
class ChromaVectorStore(VectorStoreInterface):
    """In-memory, fast, session-based."""
    
    def __init__(self, embedding_model: str = "text-embedding-004"):
        self.embedding = GoogleGenerativeAIEmbeddings(model=embedding_model)
        self._collections: Dict[str, Chroma] = {}  # Cache per session
    
    def _get_collection(self, collection_id: str) -> Chroma:
        """Get or create collection."""
        if collection_id not in self._collections:
            self._collections[collection_id] = Chroma(
                collection_name=collection_id,
                embedding_function=self.embedding
            )
        return self._collections[collection_id]
    
    def add_documents(self, documents: List[Document], collection_id: str) -> None:
        collection = self._get_collection(collection_id)
        collection.add_documents(documents)
    
    def query(self, query: str, collection_id: str, k: int = 3) -> List[Document]:
        collection = self._get_collection(collection_id)
        retriever = collection.as_retriever(search_kwargs={"k": k})
        return retriever.invoke(query)
    
    def delete_collection(self, collection_id: str) -> None:
        if collection_id in self._collections:
            del self._collections[collection_id]

    def get_all(self, collection_id: str):
        store = self._get_collection(collection_id)
        all_data = store._collection.get(
        include=["documents", "metadatas",]  
        )

        # Nå har du en dict med lister:
        texts = all_data["documents"]         
        metadatas = all_data["metadatas"]     
        ids = all_data["ids"]
        all_docs = [
        Document(
            page_content=text,
            metadata=meta,
            id=id_   # valgfritt, men fint å ha
        )
        for text, meta, id_ in zip(texts, metadatas, ids)]
    
        return all_docs


# ============================================
#           BIGQUERY IMPLEMENTATION
# ============================================
class BigQueryVectorStore(VectorStoreInterface):
    """Persistent, expensive, cross-session."""
    
    def __init__(self, 
                 dataset: str = "vector_store",
                 region: str = "europe-north2",
                 embedding_model: str = "text-embedding-004"):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset = dataset
        self.region = region
        self.embedding = GoogleGenerativeAIEmbeddings(model=embedding_model)
        self._stores: Dict[str, BigQueryVectorStore] = {}
    
    def _get_store(self, table_name: str) -> BigQueryVectorStore:
        if table_name not in self._stores:
            self._stores[table_name] = BigQueryVectorStore(
                project_id=self.project_id,
                dataset_name=self.dataset,
                table_name=table_name,
                location=self.region,
                embedding=self.embedding
            )
        return self._stores[table_name]
    
    def add_documents(self, documents: List[Document], table_name: str) -> None:
        store = self._get_store(table_name)
        store.add_documents(documents)
    
    def query(self, query: str, table_name: str, k: int = 3) -> List[Document]:
        store = self._get_store(table_name)
        retriever = store.as_retriever(search_kwargs={"k": k})
        return retriever.invoke(query)
    
    def delete_collection(self, table_name: str) -> None:
        # Implement BQ table deletion if needed
        pass


# ============================================
#           DOCUMENT PROCESSOR (ISOLATED)
# ============================================
class DocumentProcessor:
    """Handles ONLY parsing - no storage logic."""
    
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
    
    def parse_pdf(self, content_bytes: bytes, metadata: dict) -> List[Document]:
        reader = PdfReader(BytesIO(content_bytes))
        docs = []
        base_meta = metadata | {
            "total_pages": len(reader.pages),
            "creator": reader.metadata.get("/Creator") if reader.metadata else None
        }
        
        for i, page in enumerate(reader.pages):
            docs.append(Document(
                page_content=page.extract_text(),
                metadata={**base_meta, "page": i + 1}
            ))
        return docs
    
    def parse_text(self, text: str, metadata: dict) -> List[Document]:
        chunks = self.splitter.split_text(text)
        return [
            Document(
                page_content=chunk,
                metadata={**metadata, "chunk": i, "total_chunks": len(chunks)}
            )
            for i, chunk in enumerate(chunks)
        ]
    
    def process_attachment(self, attachment: AttachmentModel, session_id : str) -> List[Document]:
        if attachment.file_type == "application/pdf":
            content_bytes = base64.b64decode(attachment.content)
            return self.parse_pdf(
                content_bytes,
                metadata={"file_id": attachment.file_id, "session_id": session_id})
        else:
            return self.parse_text(
                attachment.content,
                metadata={"file_id": attachment.file_id, "session_id": session_id}
            )
            


