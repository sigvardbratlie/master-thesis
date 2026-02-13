
import PyPDF2
from pathlib import Path
import re
from email import policy
from email.parser import BytesParser
from pydantic import BaseModel
from email.utils import parsedate_to_datetime
from typing import Optional
import logging
from datetime import datetime, timezone
import docx
import openpyxl
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from langchain_core.documents import Document
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ParsedAttachment(BaseModel):
    filename : str
    content : bytes

class ParsedEmail(BaseModel):
    sender : str
    receiver : str
    subject : str
    timestamp : Optional[datetime]
    body : str
    attachments : Optional[list[ParsedAttachment]] = []



class LovdataAPI:
    def __init__(self):
        self.base = "https://api.lovdata.no/"
    def list_all_files(self,):
        url = self.base + "/v1/publicData/list"
        try:
            response = requests.get(url)
            response.raise_for_status()  
            return response.json()  
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None

    def get_file(self, filename : str):
        url = self.base + f"/v1/publicData/get/{filename}"
        try:
            response = requests.get(url)
            response.raise_for_status()  
            return response.content 
        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None


class ExtractLovData:
    def __init__(self):
        self.CONTENT_CLASSES = ["legalP", "numberedLegalP"]


    def extract_metadata(self, header) -> dict:
        """
        Extract document-level metadata from header section.
        """

        def get_value(cls):
            tag = header.find("dd", {"class": cls})
            if not tag:
                return None
            return tag.get_text(strip=True)

        return {
            "date_code": get_value("legacyID"),
            "document_id": get_value("dokid"),
            "department": get_value("ministry"),
            "in_force_from": get_value("dateInForce"),
            "last_amendment_effective": get_value("lastChangeInForce"),
            "last_amended_by": get_value("lastChangedBy"),
            "legal_area": get_value("legalArea"),
            "rettet": get_value("lastupdated"),
            "short_title": get_value("titleShort"),
            "title": get_value("title"),
            "other_about_document": get_value("miscInformation"),
            "ref_id": get_value("refid"),
        }

    def _is_repealed(self, article) -> bool:
        """
        Check if a paragraph is repealed, either by data-repealeddate attribute
        or by '(Opphevet)' in the title.
        """
        if article.get("data-repealeddate"):
            return True
        title_span = article.find("span", {"class": "legalArticleTitle"})
        if title_span and "Opphevet" in title_span.get_text():
            return True
        return False

    def _is_not_yet_in_force(self, article) -> bool:
        """
        Check if a paragraph is enacted but not yet in force.
        Detected by 'Tilføyes ved' in changesToParent and no legalP/numberedLegalP content.
        """
        changes = article.find("article", {"class": "changesToParent"})
        if changes and "Tilføyes ved" in changes.get_text():
            return True
        return False
    
    def build_row(self, article, metadata: dict) -> dict:
        """
        Build a single BigQuery row from a legalArticle element.
        Returns empty dict if no content (repealed, not yet in force, or genuinely missing).
        """

        paragraph_id = article.get("id")
        data_name = article.get("data-name")
        data_url = article.get("data-lovdata-URL")
        is_repealed = self._is_repealed(article)

        # § nummer
        header = article.find("span", {"class": "legalArticleValue"})
        paragraph_number = header.get_text(strip=True) if header else None

        # Selve teksten — hent fra både legalP og numberedLegalP
        content_parts = []

        for p in article.find_all("article", {"class": self.CONTENT_CLASSES}):
            content_parts.append(p.get_text(" ", strip=True))

        content = "\n".join(content_parts)

        if not content:
            if is_repealed:
                logger.debug(f"Skipping repealed paragraph {data_name} (id={paragraph_id})")
            elif self._is_not_yet_in_force(article):
                logger.debug(f"Skipping not-yet-in-force paragraph {data_name} (id={paragraph_id})")
            else:
                logger.warning(f"No content found for active paragraph {data_name} (id={paragraph_id}) — possible parsing error")
            return {}

        return {
            "content": content,
            "date_code": metadata.get("date_code"),
            "document_id": metadata.get("document_id"),
            "department": metadata.get("department"),
            "last_amendment_effective": metadata.get("last_amendment_effective"),
            "last_amended_by": metadata.get("last_amended_by"),
            "legal_area": metadata.get("legal_area"),
            "rettet": metadata.get("rettet"),
            "short_title": metadata.get("short_title"),
            "title": metadata.get("title"),
            "other_about_document": metadata.get("other_about_document"),
            "ref_id": metadata.get("ref_id"),
            "paragraph_number": paragraph_number,
            "data_name": data_name,
            "paragraph_id": paragraph_id,
            "anna_om_dokumentet": None,
            "in_force_from": metadata.get("in_force_from"),
            "eøs-henvisning": None,
            "endrar": None,
            "endrer": None,
            "gjelder_for": None,
            "eøs-henvising": None,
            "kunngjort": None,
            "embedding_model": "google_gemini-embedding-001", 
        }

    def parse_law(self, html: str) -> list[dict]:
        """
        Parse a Lovdata HTML document and return rows ready for BigQuery.
        One row per paragraph (§).
        """

        soup = BeautifulSoup(html, "lxml")

        header = soup.find("header", {"class": "documentHeader"})
        body = soup.find("main", {"class": "documentBody"})

        metadata = self.extract_metadata(header)

        rows = []
        repealed_count = 0
        not_in_force_count = 0

        for article in body.find_all("article", {"class": "legalArticle"}):
            if self._is_repealed(article):
                repealed_count += 1
            row = self.build_row(article, metadata)
            if not row and not self._is_repealed(article) and self._is_not_yet_in_force(article):
                not_in_force_count += 1
            rows.append(row)

        active_rows = [r for r in rows if r]
        if not active_rows:
            logger.warning("No legalArticle elements with content found in document.")
        
        if repealed_count:
            logger.info(f"Skipped {repealed_count} repealed paragraph(s).")
        if not_in_force_count:
            logger.info(f"Skipped {not_in_force_count} not-yet-in-force paragraph(s).")

        return rows
    
    def process_file(self, file : Path) -> list[dict]:
        docs = []
        logger.debug(f"Processing file: {file}")
        data = self.parse_law(file.read_text(encoding="utf-8"))
        for row in data:
            if row:
                doc = Document(
                    page_content=row["content"],
                    metadata={k: v for k, v in row.items() if k != "content"}
                )
                docs.append(doc)
        logger.info(f"Extracted {len(docs)} documents from file: {file}")
        return docs

    def load_docs(self, dir_path : str):
        with open("cached_docs.json", "r") as f:
            cache = json.load(f)

        all_docs = []
        for _ , file in enumerate(Path(dir_path).glob("*.xml")):
            if file.name in cache:
                logger.info(f'Loading cached documents for {file.name}')
                all_docs.extend(Document.model_validate(do) for do in cache[file.name])
            else:
                docs = self.process_file(file)
                all_docs.extend(docs)
                cache[file.name] = [doc.model_dump(mode = "json") for doc in docs]

        with open("cached_docs.json", "w") as f:
            json.dump(cache, f)

        return all_docs


class DocumentHandler:
    def __init__(self,):
        pass


    def mk_txt_from_pdf(filepath_pdf, filepath_txt):
        with open(filepath_pdf, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            number_of_pages = len(reader.pages)
            text = ""
            for page_number in range(number_of_pages):
                page = reader.pages[page_number]
                text += page.extract_text() + "\n\n"

        with open(filepath_txt, "w", encoding="utf-8") as text_file:
            text_file.write(text)

    def parse_email(file : str) -> ParsedEmail:
        with open(file, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
        time = parsedate_to_datetime(msg.get("Date",None))
        if time is None:
            time = msg.get("Date",None)
        try:
            email = ParsedEmail(sender = msg.get("From"),
                                receiver=msg.get("To"),
                                subject=msg.get("Subject",None),
                                timestamp=time,
                                body=msg.get_body(preferencelist=("plain",)).get_content(),
                                )

            for part in msg.iter_attachments():
                filename = part.get_filename()
                content = part.get_payload(decode=True)
                email.attachments.append(ParsedAttachment(filename=filename, content=content))

            return email
        except Exception as e:
            logger.error(f"Error parsing email {file}: {e}")
            return None

    def check_correct_format(self, file : Path):
        startswith_date = re.compile(r"^\d{4}-\d{2}-\d{2}_")
        startswith_year = re.compile(r"^\d{4}_")
        if startswith_date.match(file.name):
            logger.info(f"----ALREADY CORRECT FORMAT: {file.name}----")
            return True
        elif startswith_year.match(file.name):
            logger.info(f"----ALREADY CORRECT FORMAT: {file.name}----")
            return True
        else:
            return False
        
    def rename_email_with_dates(self, file : Path,rename = False,):
        if isinstance(file, str):
            file = Path(file)
        correct_format = self.check_correct_format(file)
        if correct_format:
            return
        if not file.suffix.lower() == ".eml":
            logger.warning(f"----NOT AN EMAIL FILE: {file.name}----")
            return

        with open(file, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)

        date = parsedate_to_datetime(msg.get("Date", None))
        if isinstance(date, datetime):
            date = date.date()
        if date is None:
            logger.warning(f"----NO DATE FOUND: {file.name}----")
            return
        if rename:
            Path(file).rename(file.parent / (str(date) + "_" + file.name))
            return True
        else:
            logger.info(str(date) + "_" + file.name)
        
    def rename_file_with_date(self, file : Path, rename = False,):
        if isinstance(file, str):
            file = Path(file)
        correct_format = self.check_correct_format(file)
        if correct_format:
            return
        
        pattern_date = re.compile(r"\d{4}-\d{2}-\d{2}")
        pattern_year = re.compile(r"\d{4}")
        pattern_date_alt = re.compile(r"\d{6}")
        match_date = pattern_date.search(file.name)
        match_year = pattern_year.search(file.name)
        match_date_alt = pattern_date_alt.search(file.name)
        if match_date:
            new_filename = match_date.group(0) + "_" + file.name
            if rename:
                file.rename(file.parent / new_filename)
                return True
            else:
                logger.info(new_filename)
        elif match_date_alt:
            date_str = match_date_alt.group(0)
            year = "20" + date_str[4:6]
            month = date_str[2:4]
            day = date_str[0:2]
            if int(year) < 1900:
                logger.warning(f"----INVALID YEAR FOUND: {file.name} (before 1900)----")
                return
            new_filename = f"{year}-{month}-{day}_" + file.name
            if rename:
                file.rename(file.parent / new_filename)
                return True
            else:
                logger.info(new_filename)
        
        elif match_year:
            if int(match_year.group(0)) < 1900:
                logger.warning(f"----INVALID YEAR FOUND: {file.name} (before 1900)----")
                return
            new_filename = match_year.group(0) + "_" + file.name
            if rename:
                file.rename(file.parent / new_filename)
                return True
            else:
                logger.info(new_filename)
        
        
        else:
            logger.warning(f"----NO DATE FOUND: {file.name}----")

    def parse_pdf_date(s: str):
        if not s or not s.startswith("D:"):
            return None

        s = s[2:]
        dt = datetime(
            int(s[0:4]), int(s[4:6]), int(s[6:8]),
            int(s[8:10]), int(s[10:12]), int(s[12:14]),
            tzinfo=timezone.utc
        )
        return dt

    def rename_pdf_with_date(self, file, rename=False, create_date : bool = True):
        '''Rename PDF file with creation date from metadata.'''
        if isinstance(file, str):
            file = Path(file)
        correct_format = self.check_correct_format(file)
        if correct_format:
            return
        if not file.suffix.lower() == ".pdf":
            logger.warning(f"----NOT A PDF FILE: {file.name}----")
            return
        with open(file, 'rb') as f:
            txt = ""
            reader = PyPDF2.PdfReader(f)
            meta = reader.metadata
            for page in reader.pages:
                txt += page.extract_text()
            
            if (meta.get('/CreationDate') or meta.get('/ModDate')) and txt:
                if create_date and meta.get('/CreationDate'):
                    date = self.parse_pdf_date(meta['/CreationDate'])
                else:
                    date = self.parse_pdf_date(meta['/ModDate'])
                if rename:
                    Path(file).rename(file.parent / (str(date) + "_" + file.name))
                    return True
                else:
                    logger.info(str(date) + "_" + file.name)
            else:
                if not meta:
                    logger.warning(f"----NO METADATA FOUND: {file.name}----")
                if not txt:
                    logger.warning(f"----NO TEXT FOUND: {file.name}----")

    def rename_xlsx_with_date(self, file : Path, rename=False):
        '''Rename XLSX file with creation date from metadata.'''
        if isinstance(file, str):
            file = Path(file)
        
        correct_format = self.check_correct_format(file)
        if correct_format:
            return
        if not file.suffix.lower() == ".xlsx":
            logger.warning(f"----NOT A XLSX FILE: {file.name}----")
            return
        wb = openpyxl.load_workbook(file, read_only=True)
        props = wb.properties
        props.created
        if rename:
            file.rename(file.parent / f"{props.created.date()}_{file.name}")
            return True
        else:
            logger.info(f"{props.created.date()}_{file.name}")

    def rename_docx_with_date(self, file : Path, rename=False):
        if isinstance(file, str):
            file = Path(file)
        correct_format = self.check_correct_format(file)
        if correct_format:
            return
        if not file.suffix.lower() == ".docx":
            logger.warning(f"----NOT A DOCX FILE: {file.name}----")
            return
        doc = docx.Document(file)
        date = doc.core_properties.created
        if not date:
            logger.warning(f"----NO DATE FOUND: {file.name}----")
            return
        if rename:
            Path(file).rename(file.parent / (str(doc.core_properties.created.date()) + "_" + file.name))
            return True
        else:
            logger.info(str(doc.core_properties.created.date()) + "_" + file.name)



