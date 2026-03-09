import logging
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List


logger = logging.getLogger(__name__)


class BaseHandler:
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
