
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

def check_correct_format(file : Path):
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
    


def rename_email_with_dates(file : Path,rename = False,):
    if isinstance(file, str):
        file = Path(file)
    correct_format = check_correct_format(file)
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
    

def rename_file_with_date(file : Path, rename = False,):
    if isinstance(file, str):
        file = Path(file)
    correct_format = check_correct_format(file)
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


def rename_pdf_with_date(file, rename=False, create_date : bool = True):
    '''Rename PDF file with creation date from metadata.'''
    if isinstance(file, str):
        file = Path(file)
    correct_format = check_correct_format(file)
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
                date = parse_pdf_date(meta['/CreationDate'])
            else:
                date = parse_pdf_date(meta['/ModDate'])
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


def rename_xlsx_with_date(file : Path, rename=False):
    '''Rename XLSX file with creation date from metadata.'''
    if isinstance(file, str):
        file = Path(file)
    
    correct_format = check_correct_format(file)
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

def rename_docx_with_date(file : Path, rename=False):
    if isinstance(file, str):
        file = Path(file)
    correct_format = check_correct_format(file)
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