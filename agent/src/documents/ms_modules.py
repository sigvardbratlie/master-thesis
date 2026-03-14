from io import BytesIO
import logging
from langchain_core.documents import Document
from models import VectorStoreMetadata,FileType,  WriteDocx
from docx import Document as DocxDocument
from pptx import Presentation
from .base_module import BaseHandler


logger = logging.getLogger(__name__)


class DocxHandler(BaseHandler):
    def __init__(self,chunk_size : int = 1000, chunk_overlap : int = 200):
        '''Handler for parsing DOCX documents.
        Args:
            chunk_size (int): The maximum size of each text chunk extracted from the DOCX. (default: Splits by paragraph)
            chunk_overlap (int): The number of characters to overlap between chunks. (default: 200)
        '''
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def parse_docx_to_docs(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> list[Document]:
        try:
            word_doc = DocxDocument(BytesIO(content))
        except Exception as e:
            logger.error(f"❌ Failed to load DOCX: {e} ({metadata.get('filename', 'unknown')})")
            return []

        props = word_doc.core_properties
        metadata_full = {
            **metadata,
            "title": props.title,
            "creator": props.author,
            "created_at": props.created.isoformat() if props.created else None,
            "updated_at": props.modified.isoformat() if props.modified else None,
            "comments": props.comments,
            "language": props.language,
            "file_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        final_metadata = VectorStoreMetadata.model_validate(metadata_full).model_dump() if force_metadata_model else metadata_full

        return [
            Document(page_content=para.text.strip(), metadata={**final_metadata, "chunk": i+1, "total_chunks": len(word_doc.paragraphs)})
            for i, para in enumerate(word_doc.paragraphs)
            if para.text.strip()
        ]

    def mk_docx(self, docx_data : WriteDocx) -> bytes:
        doc = DocxDocument()
        if docx_data.heading:
            doc.add_heading(docx_data.heading, level=1)
        for para in docx_data.paragraphs:
            doc.add_paragraph(para)
        with BytesIO() as output:
            doc.save(output)
            return output.getvalue()
        
class XlsxHandler(BaseHandler):
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    
    def parse_xlsx_to_docs(self, content: bytes, metadata: dict) -> list[Document]:
        logger.warning(f"⚠️  XLSX parsing not implemented yet {metadata.get('filename', 'unknown')}")
        return []
    
class PptxHandler(BaseHandler):
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def parse_pptx_to_docs(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> list[Document]:
        try:
            ppt_doc = Presentation(BytesIO(content))
        except Exception as e:
            logger.error(f"❌ Failed to load PPTX: {e} ({metadata.get('filename', 'unknown')})  ")
            return []

        props = ppt_doc.core_properties
        metadata_full = {
            **metadata,
            "title": props.title,
            "creator": props.author,
            "created_at": props.created.isoformat() if props.created else None,
            "updated_at": props.modified.isoformat() if props.modified else None,
            "comments": props.comments,
            "language": props.language,
            "file_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        final_metadata = VectorStoreMetadata.model_validate(metadata_full).model_dump() if force_metadata_model else metadata_full

        docs = []
        for i, slide in enumerate(ppt_doc.slides):
            slide_text = "\n".join(shape.text.strip() for shape in slide.shapes if hasattr(shape, "text")).strip()
            if slide_text:
                docs.append(Document(page_content=slide_text, metadata={**final_metadata, "chunk": i+1, "total_chunks": len(ppt_doc.slides)}))
        return docs

