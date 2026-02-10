import os
from io import BytesIO
import tempfile
from PyPDF2 import PdfReader
import logging
import base64
from datetime import datetime
from typing import List, Dict, Literal

from langchain_core.messages import SystemMessage
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_chroma import Chroma

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_google_community import BigQueryVectorStore

from google.cloud import bigquery
from google.cloud import bigquery

from models.api_request_models import AttachmentModel, EmailModel
import ocrmypdf
from email.message import Message
import email
import uuid

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
    
    def add_documents(self, documents: List[Document], collection_id: str, add_embeddings_meta = True) -> None:
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
    
    def query(self, query: str, collection_id: str, k: int = 3) -> List[Document]:
        store = self._get_store(collection_id)
        retriever = store.as_retriever(search_kwargs={"k": k})
        return retriever.invoke(query)
    
    def delete_collection(self, collection_id: str) -> None:
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
    
    @staticmethod
    def to_plain_text(docs: List[Document]) -> str:
        """Extract concatenated text from documents."""
        return "\n\n".join([d.page_content for d in docs])
    
    @staticmethod
    def to_dict(docs: List[Document]) -> List[dict]:
        """Convert to dict for JSON/BigQuery."""
        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]

    # =============================
    #      HELPER METHODS
    # =============================

    def _needs_ocr(self, content: bytes) -> bool:
        """Detect if PDF needs OCR based on text density."""
        try:
            reader = PdfReader(BytesIO(content))
            total_pages = len(reader.pages)
            pages_with_text = 0
            total_text_length = 0
            
            for page in reader.pages:
                text = page.extract_text().strip()
                if text and len(text) > 50:  # More than metadata/page numbers
                    pages_with_text += 1
                    total_text_length += len(text)
            
            # Heuristikk: Hvis < 50% av sidene har tekst ELLER veldig lite tekst per side
            text_coverage = pages_with_text / total_pages if total_pages > 0 else 0
            avg_text_per_page = total_text_length / total_pages if total_pages > 0 else 0
            
            return text_coverage < 0.5 or avg_text_per_page < 100
        except Exception as e:
            logger.warning(f"Could not analyze PDF for OCR need: {e}")
            return False  # Default to no OCR if detection fails

    def _ocr_bytes(self, content: bytes) -> bytes:
        """OCR a PDF with improved error handling."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as inp, \
            tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as out:
            
            try:
                inp.write(content)
                inp.flush()
                inp.close()  # Close before OCR reads it
                
                ocrmypdf.ocr(
                    inp.name,
                    out.name,
                    deskew=True,
                    redo_ocr=True,  # Better than force_ocr - skips already-OCR'd pages
                    skip_text=False,  # Keep existing text
                    optimize=1,  # Light optimization
                    force_ocr=False  # Don't re-OCR text pages
                )
                
                with open(out.name, 'rb') as f:
                    return f.read()
                    
            except ocrmypdf.exceptions.PriorOcrFoundError:
                logger.info("PDF already has OCR text, returning original")
                return content
            except Exception as e:
                logger.error(f"OCR failed: {e}, returning original PDF")
                return content
            finally:
                # Cleanup temp files
                for f in [inp.name, out.name]:
                    try:
                        os.unlink(f)
                    except:
                        pass
    
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

    # def _extract_attachments(self, msg : Message) -> list:
    #     attachments = []
    #     for part in msg.walk():
    #         content_disposition = part.get("Content-Disposition")
    #         if content_disposition and "attachment" in content_disposition:
    #             filename = part.get_filename()
    #             if filename:
    #                 attachments.append({
    #                     "filename": filename,
    #                     "file_type": part.get_content_type(),
    #                     "size" : len(part.get_payload(decode=True)),
    #                     "file_id": str(uuid.uuid4()),
    #                     "content": part.get_payload(decode=True).decode("utf-8")
    #                 })
    #     return attachments
 
    # def _extract_email_data(self, msg : Message, query_id : str, user_id: str , session_id : str) -> dict:
    #     attachments_list = self._extract_attachments(msg)
    #     attachments = []
    #     att_ids = []
    #     if attachments_list:
    #         for att in attachments_list:
    #             ext = os.path.splitext(att["filename"])[1].lower()
    #             attachment_model = AttachmentModel(
    #                 filename=att["filename"],
    #                 file_id=att["file_id"],
    #                 file_type=att["file_type"],
    #                 size=att["size"],
    #                 content=att["content"],
    #                 query_id=query_id,
    #                 event_id=None,
    #                 path = f'{user_id}/{session_id}/{att.get("file_id")}.{ext}'
    #             )
    #             attachments.append(attachment_model)
    #             att_ids.append(att["file_id"])
    #     email_data = EmailModel(
    #             email_id=str(uuid.uuid4()),
    #             subject=msg.get("Subject", ""),
    #             sender=msg.get("From", ""), 
    #             recipients=msg.get("To", "").split(","),
    #             cc=msg.get("Cc", "").split(",") if msg.get("Cc") else None,
    #             bcc=msg.get("Bcc", "").split(",") if msg.get("Bcc") else None,
    #             email_date=email.utils.parsedate_to_datetime(msg.get("Date")),
    #             body_text=self._extract_email_body(msg).get("text", ""),
    #             body_html=self._extract_email_body(msg).get("html", None),
    #             headers=dict(msg.items()) if msg.items() else None,
    #             attachments= att_ids,
    #             query_id=query_id,
    #         )
    
    #     return {"email" : email_data, "attachments" : attachments if attachments else []}

    # ============================
    #      MAIN PARSE METHODS
    # ============================
    
    def parse_pdf(self, content: bytes, metadata: dict) -> List[Document]:
        if self._needs_ocr(content):
            logger.info("PDF needs OCR, processing...")
            content = self._ocr_bytes(content)
        
        count_without_text = 0
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as e:
            logger.error(f"Error reading PDF: {e}")
            return []
        docs = []
        base_meta = metadata | {
            "total_pages": len(reader.pages),
            "creator": reader.metadata.get("/Creator") if reader.metadata else None
        }
        
        for i, page in enumerate(reader.pages):
            txt = page.extract_text().strip() if page.extract_text() else ""
            if not txt:
                count_without_text += 1
                logger.debug(f"Page {i + 1} has no extractable text.")
                continue
                # docs.append(Document(
                #     page_content="No text",
                #     metadata={**base_meta, "page": i + 1, "note": "No extractable text"}
                # ))
            else:
                docs.append(Document(
                    page_content=txt,
                    metadata={**base_meta, "page": i + 1}
                ))
            
        if not docs or count_without_text == len(reader.pages):
            logger.warning("No pages extracted from PDF.")
            return []
        logger.debug(f"Extracted {len(docs)} pages with text out of {len(reader.pages)} total pages.")
        return docs
    
    def parse_text(self, content : bytes, metadata: dict) -> List[Document]:
        text = content.decode('utf-8', errors='ignore')
        try:
            chunks = self.splitter.split_text(text)
        except Exception as e:
            logger.error(f"Error splitting text: {e}")
            chunks = [text]  # Fallback to whole text if splitting fails

        if not chunks:
            logger.warning("No chunks created from text.")
            return []
        try:
            return [
                Document(
                    page_content=chunk,
                    metadata={**metadata, "chunk": i, "total_chunks": len(chunks)}
                )
                for i, chunk in enumerate(chunks)
            ]
        except Exception as e:
            logger.error(f"Error creating Document objects: {e}")
            return []

    def parse_eml(self, content: bytes, metadata : dict) -> list[Document]:
        '''Process EML content and extract email data and attachments
        
        Args:
            content (str): The EML content as a base64 encoded string.
            user_id (str): The ID of the user associated with the email.
            query_id (str): The ID of the query associated with the email.
            session_id (str): The ID of the session associated with the email.
        Returns:
            dict: A dictionary containing the extracted email data and attachments.
        
        '''
        try:
            msg = email.message_from_bytes(content)
        except Exception as e:
            logger.error(f"Error parsing EML content: {e}", exc_info=True)
            raise ValueError("Invalid EML content") from e
        body = self._extract_email_body(msg)
        chunks = self.splitter.split_text(body.get("text", ""))
        docs = []
        if not chunks:
            logger.warning("No text chunks created from email body.")
            chunks = [body.get("text", "")]
        for i, chunk in enumerate(chunks):
            logger.debug(f"Chunk {i + 1}/{len(chunks)}: {chunk[:100]}...")  # Log first 100 chars of each chunk
            docs.append(Document(page_content=chunk, metadata={**metadata, "chunk": i, "total_chunks": len(chunks)}))
        return docs
    
    def parse_csv(self, content: bytes, metadata: dict) -> list[Document]:
        content_decoded = content.decode('utf-8', errors='ignore')
        docs = []
        chunks = self.splitter.split_text(content_decoded)
        if not chunks:
            logger.warning("No chunks created from CSV content.")
            chunks = [content_decoded]
        for i, chunk in enumerate(chunks):
            logger.debug(f"Chunk {i + 1}/{len(chunks)}: {chunk[:100]}...")  # Log first 100 chars of each chunk
            docs.append(Document(page_content=chunk, metadata={**metadata, "chunk": i, "total_chunks": len(chunks)}))
        return docs
        
    def parse_xlsx(self, content: bytes, metadata: dict) -> list[Document]:
        logger.warning("XLSX parsing not implemented yet.")
        return []
    
    def parse_docx(self, content: bytes, metadata: dict) -> list[Document]:
        #text = 
        pass

    def parse(self, content : str, 
                           file_type : Literal["application/pdf", 
                                               "text/plain", 
                                               "text/csv", 
                                               "message/rfc822", 
                                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"], 
                           metadata : dict = None) -> List[Document]:
        '''Main entry point for parsing attachments. Handles different file types and routes to appropriate parsers.
        Args:
            content (str): The content of the attachment, expected to be a base64 encoded string.
            file_type (str): The MIME type of the file, used to determine parsing method.
            metadata (dict): Additional metadata to attach to each Document, such as file_id and session_id.
        Returns:
            List[Document]: A list of Document objects extracted from the attachment, ready for embedding and storage.
        '''

        if "file_id" not in metadata or "session_id" not in metadata:
            logger.error("Metadata must include 'file_id' and 'session_id'")
            raise ValueError("Metadata must include 'file_id' and 'session_id'")
        
        try:
            content_decoded = base64.b64decode(content)
        except Exception as e:
            logger.error(f"Failed to decode base64 content for attachment {metadata.get('file_id')}: {e}")
            return []
        
        if file_type == "application/pdf":
            return self.parse_pdf(content_decoded, metadata=metadata)
        elif file_type == "text/plain":
            return self.parse_text(content_decoded.decode('utf-8', errors='ignore'), metadata=metadata)
        elif file_type == "text/csv":
            return self.parse_csv(content_decoded, metadata=metadata)
        elif file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            return self.parse_xlsx(content_decoded, metadata=metadata)
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return self.parse_docx(content_decoded, metadata=metadata)
        elif file_type == "message/rfc822":
            return self.parse_eml(content_decoded, metadata=metadata)
        else:
            logger.warning(f"Unsupported file type {file_type} for attachment {metadata.get('file_id')}")
            return []
            


