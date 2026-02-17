import os
import logging
from datetime import datetime
from typing import List, Dict
from langchain_core.documents import Document

from langchain_chroma import Chroma

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from abc import ABC, abstractmethod
from typing import List, Dict
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
    
    def __init__(self, embedding_model: str = "google_gemini-embedding-001"):
        self.embedding_model = embedding_model
        if embedding_model.split("_")[0] == "google":
            model_name = embedding_model.split("_")[1]
            embedding = GoogleGenerativeAIEmbeddings(model=model_name)
        else:
            logger.warning(f"Unknown embedding model {embedding_model}, defaulting to gemini-embedding-001")
            embedding = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
        
        self.embedding = embedding
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
        try:
            collection.add_documents(documents)
        except Exception as e:
            logger.error(f"Error adding documents to collection {collection_id}: {e}")

    def add_embeddings_meta(self, document : Document, ) -> None:
        """Add metadata to document before embedding."""
        metadata = document.metadata or {}
        metadata.update({
            "added_at": datetime.now().isoformat(),
            "embedding_model": self.embedding_model,
        })
        document.metadata = metadata
    
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
class BQVectorStore(VectorStoreInterface):
    """Persistent, expensive, cross-session."""
    
    def __init__(self, 
                 dataset: str = "vector_store",
                 region: str = "europe-north2",
                 embedding_model: str = "google_gemini-embedding-001"):
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.dataset = dataset
        self.region = region
        self.client = bigquery.Client(project=self.project_id)

        self.embedding_model = embedding_model
        if embedding_model.split("_")[0] == "google":
            model_name = embedding_model.split("_")[1]
            embedding = GoogleGenerativeAIEmbeddings(model=model_name)
        else:
            logger.warning(f"Unknown embedding model {embedding_model}, defaulting to gemini-embedding-001")
            embedding = GoogleGenerativeAIEmbeddings(model="gemini-embedding-001")
        
        self.embedding = embedding        
        self._stores: Dict[str, BigQueryVectorStore] = {}
    
    def _get_store(self, collection_id: str) -> BigQueryVectorStore:
        if collection_id not in self._stores:
            self._stores[collection_id] = BigQueryVectorStore(
                project_id=self.project_id,
                dataset_name=self.dataset,
                table_name=collection_id,
                location=self.region,
                embedding=self.embedding
            )
        return self._stores[collection_id]
    
    def add_documents(self, documents: List[Document], collection_id: str = "attachments", add_embeddings_meta = True) -> None:
        if add_embeddings_meta:
            for doc in documents:
                self.add_embeddings_meta(doc)
                
        store = self._get_store(collection_id)
        store.add_documents(documents)

    def add_embeddings_meta(self, document : Document, ) -> None:
        """Add metadata to document before embedding."""
        metadata = document.metadata or {}
        metadata.update({
            "embedding_model": self.embedding_model,
        })
        document.metadata = metadata
    
    def query(self, query: str, collection_id: str = "attachments", k: int = 3, filter= {}) -> List[Document]:
        store = self._get_store(collection_id)
        retriever = store.as_retriever(search_kwargs={"k": k},
                                       filter = filter)
        return retriever.invoke(query)
    
    def delete_project(self, project_id: str,collection_id: str= "attachments") -> None:
        self.client.query(f"DELETE FROM vector_store.{collection_id} WHERE project_id = '{project_id}'").result()
    
    def delete_file(self, file_id: str, collection_id: str = "attachments") -> None:
        self.client.query(f"DELETE FROM vector_store.{collection_id} WHERE file_id = '{file_id}'").result()




