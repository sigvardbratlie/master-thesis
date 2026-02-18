from pathlib import Path
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from langchain_core.documents import Document
from dotenv import load_dotenv
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()


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

