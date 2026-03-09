import logging
from langchain_core.documents import Document
from typing import List

from models import FileType

from .base_module import BaseHandler
from .email_module import EmailHandler
from .ms_modules import DocxHandler, PptxHandler, XlsxHandler
from .pdf_module import PDFHandler
from .text_module import TextHandler


logger = logging.getLogger(__name__)

    
class DocumentProcessor(BaseHandler):
    """Handles parsing of various document types into Document objects, ready for embedding and storage. Delegates to specific handlers based on file type."""
    
    def __init__(self,):
        pass

    def map_file_type(self, file_suffix: str) -> FileType:
        """Maps file suffix to MIME type for parsing. Defaults to 'unknown/unknown' if not recognized."""
        mapping = {
            ".pdf":"application/pdf",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".csv": "text/csv",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".xlsx" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            ".eml": "message/rfc822",
        }
        return mapping.get(file_suffix, "unknown/unknown")

    def parse(self, content: bytes,
              file_type: FileType,
              metadata: dict = None,
              force_metadata_model: bool = True) -> List[Document]:
        '''Main entry point for parsing attachments. Handles different file types and routes to appropriate parsers.
        Args:
            content (bytes): The raw binary content of the attachment.
            file_type (str): The MIME type of the file, used to determine parsing method.
            metadata (dict): Additional metadata to attach to each Document, such as file_id and session_id.
            force_metadata_model (bool): Validate and serialize metadata through VectorStoreMetadata. Defaults to True.
        Returns:
            List[Document]: A list of Document objects extracted from the attachment, ready for embedding and storage.
        '''

        # if "file_id" not in metadata or "session_id" not in metadata or "embedding_model" not in metadata:
        #     logger.error("❌ Metadata missing required fields: 'file_id', 'session_id', 'embedding_model'")
        #     raise ValueError("Metadata must include 'file_id', 'session_id', and 'embedding_model'")

        kwargs = {"metadata": metadata, "force_metadata_model": force_metadata_model}
        if file_type == "application/pdf":
            return PDFHandler().parse_pdf_to_docs(content, **kwargs)
        elif file_type in ["text/plain", "text/markdown"]:
            return TextHandler().parse_text_to_docs(content, **kwargs)
        elif file_type == "text/csv":
            return TextHandler().parse_csv_to_docs(content, **kwargs)
        elif file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            return XlsxHandler().parse_xlsx_to_docs(content, **kwargs)
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return DocxHandler().parse_docx_to_docs(content, **kwargs)
        elif file_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            return PptxHandler().parse_pptx_to_docs(content, **kwargs)
        elif file_type == "message/rfc822":
            return EmailHandler().parse_eml_to_docs(content, **kwargs)
        else:
            logger.warning(f"⚠️  Unsupported file type '{file_type}' for {metadata.get('file_id')}")
            return []




    
