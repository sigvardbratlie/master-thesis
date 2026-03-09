from .document_module import DocumentProcessor
from .email_module import EmailHandler
from .email_module import EmailHandler
from .ms_modules import DocxHandler, PptxHandler, XlsxHandler
from .pdf_module import PDFHandler
from .text_module import TextHandler

__all__ = [
    "DocumentProcessor",
    "EmailHandler",
    "DocxHandler",
    "PDFHandler",
    "PptxHandler",
    "TextHandler",
    "XlsxHandler",
]