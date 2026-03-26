import logging
from langchain_core.documents import Document

from models import FileType

from .base_module import BaseHandler
from .email_module import EmailHandler
from .ms_modules import DocxHandler, PptxHandler, XlsxHandler
from .pdf_module import PDFHandler
from .text_module import TextHandler
from utils import AppConfig

logger = logging.getLogger(__name__)

    
class DocumentProcessor(BaseHandler):
    """Handles parsing of various document types into Document objects, ready for embedding and storage. Delegates to specific handlers based on file type."""
    
    def __init__(self,config : AppConfig = None):
        vs = config.vectorstore if config else None
        super().__init__(
            chunk_size=vs.chunk_size if vs else 1000,
            chunk_overlap=vs.chunk_overlap if vs else 200,
        )
        self.config = config

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
              force_metadata_model: bool = True,
              ocr: bool | None = None) -> tuple[str, dict]:
        '''Main entry point for parsing attachments. Handles different file types and routes to appropriate parsers.
        Args:
            content (bytes): The raw binary content of the attachment.
            file_type (str): The MIME type of the file, used to determine parsing method.
            metadata (dict): Additional metadata to attach to each Document, such as file_id and session_id.
            force_metadata_model (bool): Validate and serialize metadata through VectorStoreMetadata. Defaults to True.
        Returns:
            tuple[str, dict]: A tuple containing the parsed string content and metadata.
        '''

        # if "file_id" not in metadata or "session_id" not in metadata or "embedding_model" not in metadata:
        #     logger.error("❌ Metadata missing required fields: 'file_id', 'session_id', 'embedding_model'")
        #     raise ValueError("Metadata must include 'file_id', 'session_id', and 'embedding_model'")

        kwargs = {"metadata": metadata, "force_metadata_model": force_metadata_model}
        if file_type == "application/pdf":
            string,metadata =  PDFHandler(
                                 aws_region = self.config.storage.aws.region,
                                aws_bucket_name = self.config.storage.aws.bucket_name
                                ).parse_pdf(content, ocr=ocr, **kwargs)
        elif file_type in ["text/plain", "text/markdown"]:
            string,metadata = TextHandler().parse_text(content, **kwargs)
        elif file_type == "text/csv":
            string,metadata =   TextHandler().parse_csv(content, **kwargs)
        elif file_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            string,metadata =  XlsxHandler().parse_xlsx(content, **kwargs)
        elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            string,metadata = DocxHandler().parse_docx(content, **kwargs)
        elif file_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            string,metadata =  PptxHandler().parse_pptx(content, **kwargs)
        elif file_type == "message/rfc822":
            string,metadata = EmailHandler().parse_eml(content, **kwargs)
                               
        else:
            logger.warning(f"⚠️  Unsupported file type '{file_type}' for {metadata.get('file_id')}")
            string = ""
            metadata = {}

        return string, metadata
    
    def parse_to_docs(self, content: bytes,
              file_type: FileType,
              metadata: dict = None,
              force_metadata_model: bool = True,
              ocr: bool | None = None) -> list[Document]:
        '''Convenience method to parse content and directly return a list of Document objects.'''
        string, metadata = self.parse(content, file_type, metadata, force_metadata_model, ocr)
        return self.to_docs(string, metadata)




    
