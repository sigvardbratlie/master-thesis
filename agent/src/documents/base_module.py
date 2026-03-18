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
    
    def to_docs(self, string : str, metadata: dict) -> list[Document]:
        """Converts a long string into a list of Document objects, using the configured text splitter. Attaches metadata to each Document."""
        try:
            chunks = self.splitter.split_text(string)
        except Exception as e:
            logger.error(f"❌ Text split failed: {e} ({metadata.get('filename', 'unknown')})")
            chunks = [string]

        if not chunks:
            logger.warning(f"⚠️  No chunks created from text ({metadata.get('filename', 'unknown')})")
            return []

        return [
             Document(page_content=chunk, metadata={**metadata, "chunk": i+1, "total_chunks": len(chunks)})
             for i, chunk in enumerate(chunks)
         ]
