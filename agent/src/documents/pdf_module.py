import os
from io import BytesIO
import tempfile
import logging
from datetime import datetime, timezone, timedelta
import fitz
import pymupdf4llm

from langchain_core.documents import Document

from models import VectorStoreMetadata
import ocrmypdf

from .base_module import BaseHandler

from textractor import Textractor
from textractor.data.constants import TextractFeatures
from textractor.data.text_linearization_config import TextLinearizationConfig
from PyPDF2 import PdfReader

logger = logging.getLogger(__name__)

class PDFHandler(BaseHandler):
    '''Handler for parsing PDF documents, with optional OCR for scanned PDFs.'''
    def __init__(self,chunk_size : int = 1000, 
                      chunk_overlap : int = 200,
                      aws_bucket_name: str = "",
                      aws_region: str = "",):
        '''Handler for parsing PDF documents, with optional OCR for scanned PDFs.
        Args:
            chunk_size (int): The maximum size of each text chunk extracted from the PDF. (default: Splits by page)
            chunk_overlap (int): The number of characters to overlap between chunks. (default: 200)
        '''
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.aws_bucket_name = aws_bucket_name
        self.aws_region = aws_region

    
    def _safe_pdf_date(self,value) -> str | None:
        """Access a PyPDF2 metadata date property safely, returning None on parse errors."""
        try:
            if value is None:
                return None
            return value.isoformat() if isinstance(value, datetime) else str(value)
        except Exception:
            return None
        
    def pdf_date_to_datetime(self, pdf_date: str) -> datetime | None:
        """
        Konverterer PDF-dato-streng (f.eks. "D:20240320112610+01'00'")
        til datetime-objekt. Returnerer None ved ugyldig input.
        """
        if not pdf_date or not pdf_date.startswith("D:"):
            return None
        
        # Fjern "D:" og apostrofer (vanlig i eldre PDF-er)
        s = pdf_date[2:].replace("'", "")
        
        # Mulige formatvarianter – vi prøver de vanligste
        formats = [
            "%Y%m%d%H%M%S%z",       # D:20240320112610+0100
            "%Y%m%d%H%M%S%Z",       # D:20240320112610Z     (UTC)
            "%Y%m%d%H%M%S",         # D:20240320112610      (ingen tidssone)
            "%Y%m%d",               # D:20240320            (bare dato)
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(s, fmt)
                
                # Hvis det er %z eller %Z → allerede tidssone
                if dt.tzinfo is not None:
                    return dt
                
                # Ingen tidssone → antar UTC / lokal, her bruker vi naive → UTC
                return dt.replace(tzinfo=timezone.utc)
                
            except ValueError:
                continue
        
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

            return text_coverage < 0.7 or avg_text_per_page < 500
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
                logger.exception(f"❌ OCR failed — returning original PDF")
                return content
            finally:
                # Cleanup temp files
                for f in [inp.name, out.name]:
                    try:
                        os.unlink(f)
                    except:
                        pass
    
    def _extract_metadata(self, content: bytes) -> dict:
        doc = fitz.open(stream=content, filetype="pdf")
        meta = doc.metadata
        meta_map = {"creationDate" : "created_at",
            "modDate" : "modified_at",}
        for k,v in meta.copy().items():
            if k in meta_map and v is not None:
                meta[meta_map[k]] = self.pdf_date_to_datetime(meta.pop(k))
        meta["size"] = len(content)
        meta["file_type"] = "application/pdf"
        meta["page_count"] = doc.page_count
        doc.close()
        return meta

    def _extract_text_pypdf2(self, content : bytes) -> str:
        reader = PdfReader(BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        # metadata = {
        #     "creator": reader.metadata.creator if reader.metadata else None,
        #     "producer": reader.metadata.producer if reader.metadata else None,
        #     "created_at": self._safe_pdf_date(reader.metadata, "creation_date") if reader.metadata else None,
        #     "updated_at": self._safe_pdf_date(reader.metadata, "modification_date") if reader.metadata else None,
        #     "title": reader.metadata.subject or reader.metadata.title if reader.metadata else None,
        #     "keywords": reader.metadata.get("/Keywords") if reader.metadata else None,
        #     "size": len(content),
        #     "file_type": "application/pdf",
        # }
        return text.strip()

    def _extract_md_textract(self, content : bytes) -> str:
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(content)
            tmp_path = f.name

        config = TextLinearizationConfig(
            hide_figure_layout=False,
            title_prefix="# ",
            section_header_prefix="## ",
            table_linearization_format="markdown",
        )
        extractor = Textractor(profile_name="default", region_name=self.aws_region)

        document = extractor.start_document_analysis(
                                        file_source=tmp_path,
                                        features=[TextractFeatures.LAYOUT, TextractFeatures.TABLES],
                                        s3_output_path=f"s3://{self.aws_bucket_name}/textract-output/",
                                        s3_upload_path=f"s3://{self.aws_bucket_name}/uploads/",
                                        )
        markdown = document.get_text(config=config)
        return markdown 

    def _extract_md_pymupdf(self, content : bytes) -> str:
        doc = fitz.open(stream=content, filetype="pdf")
        markdown = pymupdf4llm.to_markdown(doc)
        doc.close()
        return markdown
    
    def parse_pdf(self, content: bytes, metadata: dict, force_metadata_model: bool = True) -> tuple[str, dict]:
        meta_pdf = self._extract_metadata(content)
        meta = {**metadata, **meta_pdf}
        if self._needs_ocr(content):
            logger.info(f"🔍 PDF needs OCR — processing with Textract... File : {metadata.get("filename", "unknown")}")
            md = self._extract_md_textract(content)
        else:
            logger.info(f"✅ PDF has extractable text — extracting with PyMuPDF... File : {metadata.get("filename", "unknown")}")
            md = self._extract_md_pymupdf(content)

        final_metadata = VectorStoreMetadata.model_validate(meta).model_dump(mode="json") if force_metadata_model else meta
        return md, final_metadata
