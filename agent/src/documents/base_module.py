import logging
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


logger = logging.getLogger(__name__)


class BaseHandler:
    """Handles ONLY parsing - no storage logic."""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    @staticmethod
    def to_plain_text(docs: list[Document]) -> str:
        """Extract concatenated text from documents."""
        return "\n\n".join([d.page_content for d in docs])
    
    @staticmethod
    def to_dict(docs: list[Document]) -> list[dict]:
        """Convert to dict for JSON/BigQuery."""
        return [{"content": d.page_content, "metadata": d.metadata} for d in docs]
