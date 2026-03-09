import logging
from langchain_core.documents import Document
from typing import List

from models import VectorStoreMetadata

from .base_module import BaseHandler



logger = logging.getLogger(__name__)


class TextHandler(BaseHandler):
    def __init__(self):
        super().__init__()

    def parse_text_to_docs(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> List[Document]:
        text = content.decode('utf-8', errors='ignore')
        try:
            chunks = self.splitter.split_text(text)
        except Exception as e:
            logger.error(f"❌ Text split failed: {e} ({metadata.get('filename', 'unknown')})")
            chunks = [text]

        if not chunks:
            logger.warning(f"⚠️  No chunks created from text ({metadata.get('filename', 'unknown')})")
            return []

        metadata_all = {**metadata, "file_size": len(content), "file_type": "text/plain"}
        final_metadata = VectorStoreMetadata.model_validate(metadata_all).model_dump() if force_metadata_model else metadata_all
        return [
            Document(page_content=chunk, metadata={**final_metadata, "chunk": i+1, "total_chunks": len(chunks)})
            for i, chunk in enumerate(chunks)
        ]
        

    def parse_csv_to_docs(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> list[Document]:
        content_decoded = content.decode('utf-8', errors='ignore')
        chunks = self.splitter.split_text(content_decoded)
        if not chunks:
            logger.warning(f"⚠️  No chunks created from CSV content ({metadata.get('filename', 'unknown')})")
            chunks = [content_decoded]

        metadata_all = {**metadata, "file_size": len(content), "file_type": "text/csv"}
        final_metadata = VectorStoreMetadata.model_validate(metadata_all).model_dump() if force_metadata_model else metadata_all
        return [
            Document(page_content=chunk, metadata={**final_metadata, "chunk": i+1, "total_chunks": len(chunks)})
            for i, chunk in enumerate(chunks)
        ]
   