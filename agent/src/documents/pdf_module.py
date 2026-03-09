import os
from io import BytesIO
import tempfile
from PyPDF2 import PdfReader
import logging
from typing import List, Optional
from datetime import datetime

from langchain_core.documents import Document

from models import VectorStoreMetadata
import ocrmypdf

from .base_module import BaseHandler



logger = logging.getLogger(__name__)

class PDFHandler(BaseHandler):
    def __init__(self):
        super().__init__()

    
    def _safe_pdf_date(self, metadata, field: str) -> Optional[datetime]:
        """Access a PyPDF2 metadata date property safely, returning None on parse errors."""
        try:
            return getattr(metadata, field)
        except Exception:
            return None

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
            
            # Heuristikk: Hvis < 50% av sidene har tekst ELLER lite meningsfullt innhold per side
            # 500 chars/page threshold skiller ekte innhold fra bare metadata/sidenumre/overskrifter
            text_coverage = pages_with_text / total_pages if total_pages > 0 else 0
            avg_text_per_page = total_text_length / total_pages if total_pages > 0 else 0

            return text_coverage < 0.5 or avg_text_per_page < 500
        except Exception as e:
            logger.warning(f"⚠️  Could not analyze PDF for OCR need: {e}")
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
                    deskew=True,  # Deskew pages for better OCR accuracy. Not compatibel with redo_ocr
                    #redo_ocr=True,  # Re-OCR entire document for better text extraction. Not compatibel with deskew
                    skip_text=False,  # Keep existing text
                    optimize=1,  # Light optimization
                    force_ocr=False,  # Don't re-OCR text pages
                    language="nor+eng" #["nor","eng"]
                )
                
                with open(out.name, 'rb') as f:
                    return f.read()
                    
            except ocrmypdf.exceptions.PriorOcrFoundError:
                logger.debug("PDF already has OCR text — skipping OCR")
                return content
            except Exception as e:
                logger.error(f"❌ OCR failed: {e} — returning original PDF")
                return content
            finally:
                # Cleanup temp files
                for f in [inp.name, out.name]:
                    try:
                        os.unlink(f)
                    except:
                        pass
    
    def parse_pdf_to_docs(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> List[Document]:
        if self._needs_ocr(content):
            logger.info("🔍 PDF needs OCR — processing...")
            content = self._ocr_bytes(content)

        count_without_text = 0
        try:
            reader = PdfReader(BytesIO(content))
        except Exception as e:
            logger.error(f"❌ Error reading PDF: {e} ({metadata.get('filename', 'unknown')})")
            return []
        base_meta = metadata | {
            "creator": reader.metadata.creator if reader.metadata else None,
            "producer": reader.metadata.producer if reader.metadata else None,
            "created_at": self._safe_pdf_date(reader.metadata, "creation_date") if reader.metadata else None,
            "updated_at": self._safe_pdf_date(reader.metadata, "modification_date") if reader.metadata else None,
            "title": reader.metadata.subject or reader.metadata.title if reader.metadata else None,
            "keywords": reader.metadata.get("/Keywords") if reader.metadata else None,
            "file_size": len(content),
            "file_type": "application/pdf",
        }
        final_metadata = VectorStoreMetadata.model_validate(base_meta).model_dump() if force_metadata_model else base_meta

        docs = []
        for i, page in enumerate(reader.pages):
            txt = page.extract_text().strip() if page.extract_text() else ""
            if not txt:
                count_without_text += 1
                logger.debug(f"Page {i + 1} has no extractable text.")
                continue
            docs.append(Document(
                page_content=txt,
                metadata={**final_metadata, "chunk": i + 1, "total_chunks": len(reader.pages)}
            ))

        if not docs or count_without_text == len(reader.pages):
            logger.warning(f"⚠️  No pages extracted from PDF {metadata.get('filename', 'unknown')} — all {count_without_text} pages had no text")
            return []
        logger.debug(f"Extracted {len(docs)} pages with text out of {len(reader.pages)} total pages from {metadata.get('filename', 'unknown')}.")
        return docs

