from importlib.resources import path
import os
import re
from dotenv import load_dotenv
import json
from typing import Optional, Literal
import logging
from datetime import date, datetime, timezone
from google.cloud import bigquery

from langchain_tavily import TavilySearch
from langchain_core.runnables import RunnableConfig
from langchain.tools import tool

from database import GCSManager, BQVectorStore, SupabaseManager
from documents import DocumentProcessor
from utils import get_app_config,setup_logging
from .utils import _parse_date

load_dotenv()
config = get_app_config()
logger = logging.getLogger(__name__)
setup_logging(config)
document_processor = DocumentProcessor(config=config)


tavily_search = TavilySearch(
    max_results=5,
    topic="general",
)

# ============ SHARED TOOLS ============
@tool
def query_project_attachments(query: str, project_id: str, k: int = 10, metadata : dict = None) -> str:
    """Function to use RAG to retrieve documents of a specific project.

    Args:
        query (str): The query to search in the vectorstore.
        project_id (str): The project id to identify which vectorstore to query.
        k (int): The number of top results to retrieve from the vectorstore. 
        metadata (dict, optional): Additional metadata to filter the vectorstore query. Defaults to None. I.e., {'file_id' : '741ef083-9335-4a55-bbe1-ea866bf01758'}.
    Returns:
        str: The retrieved information from the vectorstore based on the query.

    Available metadata fields are limited to: file_id : uuid, filename : str, file_type (MIME) : str. 
    """
    base_filter = {"project_id": project_id}
    filters = base_filter
    if metadata:
        if not isinstance(metadata, dict):
            logger.warning(f"Metadata should be a dictionary. Received {type(metadata)}. Ignoring metadata.")
        elif "file_id" not in metadata and "filename" not in metadata and "file_type" not in metadata:
            logger.warning(f"Metadata should contain at least one of the following keys: 'file_id', 'filename', 'file_type'. Received keys: {list(metadata.keys())}. Ignoring metadata.")
        else:
            filters = {**base_filter, **metadata}
    vectorstore = BQVectorStore()
    results = vectorstore.query(query=query, collection_id="attachments", k=k, filters=filters)
    if not results and filters != base_filter:
        logger.warning(f"⚠️ No results found with metadata filter {metadata} on project {project_id}. Trying without metadata filter.")
        results = vectorstore.query(query=query, collection_id="attachments", k=k, filters=base_filter)
        if not results:
            return f"No relevant information found in the vectorstore for project {project_id}."
        #res = "⚠️ No results matched the metadata filter — returning results without filter:\n"
    elif not results:
        return f"No relevant information found in the vectorstore for project {project_id}."
        
    res = "=== Retrieved relevant chunks from vectorstore: ===\n"
    for doc in results:
        res += (
            f"filename: {doc.metadata.get('filename', 'Unknown')} |"
            f"title: {doc.metadata.get('title', 'Unknown')} | "
            f"file_id: {doc.metadata.get('file_id', 'Unknown')} | "
            f"| chunk: {doc.metadata.get('chunk', 'Unknown')} of {doc.metadata.get('total_chunks', 'Unknown')} total chunks\n"
        )
        res += f"{doc.page_content}\n\n"
    return res

#CUSTOM TOOLS

@tool
def read_attachments(
    ids: list[str],
    # config : RunnableConfig
) -> str:
    """
    Reads and processes multiple attachments based on the provided file IDs.
    Content is fetched from the database body cache when available, otherwise from GCS.

    Args:
        ids (list[str]): The file IDs of the attachments to read.

    Returns:
        str: Processed content of the attachments.
    """
    db = SupabaseManager()
    storage_manager = GCSManager(config=config)
    response = db.get_body_by_id(ids=ids)
    if not response:
        logger.error(f"❌ No response from database for IDs: {ids}")
        return "❌ No content found for the provided file IDs."
    
    def process_attachment(path, content):
        try:
            file_id = (
                path.split("/")[-1].split(".")[0] if "." in path else path.split("/")[-1]
            )
            ext = "." + path.split(".")[-1] if "." in path else ""
        except Exception as e:
            logger.error(f"Error extracting file_id and extension from path: {e}")
            return None
        if ext in [".pdf", ".docx", ".pptx", ".eml", ".txt", ".md"]:
            file_type = document_processor.map_file_type(ext)
            md, _ = document_processor.parse(
                content=content,
                metadata={
                    "file_id": file_id,
                    "filename": file_id + ext,
                    "session_id": None,
                    "embedding_model": None,
                },
                file_type=file_type,
                force_metadata_model=False,
            )
            return md
        else:
            logger.error(f"Unsupported file extension: {ext}")
            return []

    results = "Results from reading attachments:" + "\n" + "-" * 50 + "\n\n"
    for i in range(len(ids)):
        res = response[i]
        content = res.get("body")
        if not content:
            read_res = storage_manager.read_attachments(paths = [res["path"]])
            raw_bytes = read_res.get(res["path"])
            content = process_attachment(res["path"], raw_bytes) if raw_bytes else None
        results +=  f"CONTENT FOR FILE-ID {ids[i]}: \n\n{content}\n\n" if content else f"No content found for file ID {ids[i]}, path {res['path']}.\n"
        results += "\n" + "-" * 50 + "\n\n"
    return results


@tool
def query_laws(query: str, 
              title : str = None,
              short_title: str = None, 
              k: int = 3) -> str:
    """Function to use RAG to retrieve relevant laws based on a query. Use this to search in laws based on a question. 
    

    Args:
        query (str): The query to search in the vectorstore. Make sure to describe the in words what you are looking for, for example the users question.
        title (str): The title of the law to filter by.
        short_title (str): The short title of the law to filter by.
        k (int): The number of top results to retrieve from the vectorstore. Default is 5.
    Returns:
        str: The retrieved information from the vectorstore based on the query.
    """
    vectorstore = BQVectorStore()

    filter_dict = {}

    if title:
        filter_dict["title"] = title

    if short_title:
        filter_dict["short_title"] = short_title

    res = ""
    if query or filter_dict:
        results = vectorstore.query(
            query=query or " ",  # dummy hvis ingen query, men bedre å ha noe
            collection_id="laws",
            k=k,
            filter=filter_dict   # BigQuery aksepterer dict-filter
        )

        if results:
            res += "=== Hentet lover med filter og/eller semantisk søk: ===\n"
            for doc in results:
                res += (
                    f"Title: {doc.metadata.get('title', 'Ukjent')} "
                    f"({doc.metadata.get('short_title', '')}) | "
                    f"{doc.metadata.get('paragraph_number', 'Ukjent')} | "
                    f"Område: {doc.metadata.get('legal_area', 'Ukjent')}\n"
                )
                res += f"{doc.page_content}\n\n"
        else:
            res += "Ingen treff med det gitte filteret eller søket.\n"

    # Fallback: rent vektorsøk uten filter hvis ingenting traff
    if not res and query:
        results = vectorstore.query(query=query, collection_id="laws", k=k)
        if results:
            res += "=== Fallback: Semantisk søk uten filter ===\n"
            for doc in results:
                res += f"Title: {doc.metadata.get('title', 'Ukjent')} | § {doc.metadata.get('paragraph_number', 'Ukjent')}\n"
                res += f"{doc.page_content}\n\n"
        else:
            res = "Ingen relevante lover funnet i databasen."

    return res.strip() or "Ingen resultater."

@tool
def read_specific_law(title: list[str], 
                      paragraph: list[str] = None) -> str:
    """Function to retrieve the content of a specific law paragraph based on title and paragraph number.

    Args:
        title (list[str]): The title(s) of the law to retrieve. For example ["Arbeidsmiljøloven", "Arbeidsmiljølova"]. Make sure to include different variations of the title to increase the chances of a match.
        paragraph (list[str], optional): The paragraph number(s) to retrieve. For example ["§3-7", § 3-8] or [§1]. If None, retrieves all paragraphs.

    Returns:
        str: The content of the specified law paragraph.
    """
    query = """
        SELECT content, title, short_title, paragraph_number
        FROM `vector_store.laws`
        WHERE EXISTS (
            SELECT 1 FROM UNNEST(@titles) AS t 
            WHERE LOWER(title) LIKE CONCAT('%', LOWER(t), '%')
        )
    """
    
    query_parameters = [
        bigquery.ArrayQueryParameter("titles", "STRING", title)
    ]

    if paragraph:
        # Vi vasker input for å fjerne mellomrom slik at "§ 1" og "§1" begge funker
        clean_paragraphs = [p.replace(" ", "") for p in paragraph]
        query += """
            AND EXISTS (
                SELECT 1 FROM UNNEST(@paragraphs) AS p 
                WHERE REPLACE(paragraph_number, ' ', '') LIKE CONCAT('%', p, '%')
            )
        """
        query_parameters.append(
            bigquery.ArrayQueryParameter("paragraphs", "STRING", clean_paragraphs)
        )

    job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
    
    try:
        # Husk å spesifisere project hvis det ikke ligger i miljøvariabler
        client = bigquery.Client() 
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        res_list = []
        for row in results:
            res_list.append(f"--- {row.paragraph_number} ---\n{row.content}")
        
        if not res_list:
            return "Ingen resultater funnet."
            
        header = f"=== Resultater for {', '.join(title)} ===\n\n"
        return header + "\n\n".join(res_list)
        
    except Exception as e:
        return f"Feil ved spørring: {str(e)}"

@tool
def update_project(
    project_id: str,
):
    """Use this function to trigger an update of the projects state to include the conversations current information"""
    return f"Project {project_id} has been sent for update"


@tool
def clean_element(
    element_type: Literal[
        "events",
        "parties",
        "title",
        "background",
        "claims",
        "deadlines",
        "damages",
        # "disputed_facts", "undisputed_facts",
    ],
    project_id: str,
):
    """Use this function to trigger a cleaning of a specific element in the projects state.
    For example, if you want to clean the vectorstore of the project, use element_type 'vectorstore'."""
    return f"Element {element_type} in project {project_id} has been sent for cleaning"


@tool
def create_project():
    """Use this function to trigger the creation of a new project in the database."""
    return "A new project has been sent for creation"


@tool
def show_elements(project_id: str, 
                  element_types: list[Literal["parties", "events", "claims", "damages", "deadlines"]], 
                    start_date: datetime | str = None, 
                    end_date: datetime | str = None, 
                    significance: list[Literal["high", "medium", "low"]] = None) -> str:
    '''
    Show elements of a project filtered by date and significance. Be specific in the element types you want to show and the date range.
    Args:
        project_id (str): The ID of the project.
        element_types (list[str]): The types of elements to show (e.g. "events", "parties", "claims", "damages", "deadlines").
        start_date (datetime): The start date for filtering elements.
        end_date (datetime): The end date for filtering elements.
        significance (list[str]): The significance levels to include (e.g. ["high", "medium"]).
    Returns:
        str: A formatted string containing the filtered elements.

    Short dictionary for norwegian-english translation: Krav -> damages, Påstander -> claims. 

    '''
    if not significance:
        significance = ["high", "medium", "low"]

    start_date = _parse_date(start_date, date.min)
    end_date = _parse_date(end_date, date.max)

    sm = SupabaseManager()
    data = sm.load_elements(project_id=project_id, 
                                tables=element_types, 
                                params = {"p_start_date" : start_date, "p_end_date" : end_date, "p_significance" : significance},
                                )

    date_col_map = {"events": "event_start_date",
                        "deadlines": "deadline_date",
                        "claims" : "source_date",
                        "damages" : "source_date",
                        }


    format_map = {
            "events": ["event_start_date", "event_name", "file_id", "description", "disputed"],
            "parties": ["legal_name", "entity_type", "role", "role_description"],
            "claims": ["party_role", "relief_sought", "factual_basis", "legal_basis", "strength_assessment", "source_date"],
            "damages": ["party_role", "category", "amount", "currency", "basis", "source_date"],
            "deadlines": ["deadline_date", "description"]}

    value = f"=== List of {', '.join(element_types)} ===\n"

    for element in element_types:
        all_elements = data.get(element, [])
        date_col = date_col_map.get(element)
        all_elements.sort(key = lambda x: x.get(date_col)) if date_col else None
        
        value += f"\n\n=== {element.upper()} ===\n"
        value += f'**FORMAT** : {" | ".join(format_map[element])}\n'
        for item in all_elements:
            #element_info = "\t" + " | ".join([f"{getattr(item, field)}" for field in format_map[element]])
            element_info = "\t" + " | ".join([f"{item.get(field)}" for field in format_map[element]])
            value += f"- {element_info}\n"
    return value

@tool
def list_attachments(
                    project_id: str,
                    element_types : list[Literal["attachments", "emails"]],
                    start_date: datetime | str = None, 
                    end_date: datetime | str = None, 
                    significance: list[Literal["high", "medium", "low"]] = None,
                  ):
    '''
    List attachments and emails of a project filtered by date and significance.
    Args:
        project_id (str): The ID of the project.
        element_types (list[str]): The types of elements to show (e.g. "events", "parties", "claims", "damages", "deadlines").
        start_date (datetime): The start date for filtering elements.
        end_date (datetime): The end date for filtering elements.
        significance (list[str]): The significance levels to include (e.g. ["high", "medium"]).
    Returns:
        str: A formatted string containing the filtered elements.

    Use the id of in `read_attachments` to read the full content of the attachment.

    '''
    if not significance:
        significance = ["high", "medium", "low"]

    start_date = _parse_date(start_date, date.min)
    end_date = _parse_date(end_date, date.max)

    sm = SupabaseManager()
    project = sm.load_attachments(project_id=project_id, 
                                tables=element_types,
                                params = {"p_start_date" : start_date, "p_end_date" : end_date, "p_significance" : significance},
                                )

    date_col_map = {"emails": "date", "attachments": "file_date"}
    format_map = {
            "emails": ["email_id", "from_addr", "date", "title"],
            "attachments": ["file_id", "file_date", "title", "category"]}
    key_map = {"emails": "email_id", "attachments": "file_id"}

    value = f"=== List of {', '.join(element_types)} ===\n"
    for item in element_types:
        all_elements = project.get(item) or []
        date_col = date_col_map.get(item)
        all_elements.sort(key = lambda x : x.get(date_col)) if date_col else None
        
        value += f"\n\n=== {item.upper()} ===\n"
        format_view = [key if key != key_map[item] else "id" for key in format_map[item]]
        value += f'**FORMAT** : {" | ".join(format_view)}\n'
        for row in all_elements:
            #element_info = "\t" + " | ".join([f"{getattr(row, field)}" for field in format_map[item]])
            element_info = "\t" + " | ".join([f"{row.get(field)}" for field in format_map[item]])
            value += f"- {element_info}\n"
    return value


# ============ RAG TOOLS ============

@tool
def list_project_attachments(project_id: str) -> str:
    '''Use this function to retrieve a list of the projects attachments with their file_ids. 
    
    Args:
        project_id (str): The project id to identify which project's attachments to list.
    Returns:
        str: A string representation of the list of attachments with their file_ids.
    '''
    client = bigquery.Client()
    query = f"""SELECT DISTINCT filename, file_id 
                FROM vector_store.attachments 
                WHERE project_id = '{project_id}'"""
    query_job = client.query(query)
    results = query_job.result()
    output = "=== List of project attachments ===\n\n"
    for row in results:
        output += f"filename: {row.filename}, file_id: {row.file_id}\n"
    return output

@tool
def read_full_attachments(file_ids: list[str]) -> str:
    '''Use this function to retrieve the full content of attachments based on their file_ids. This is a helper function that can be used in the read_attachments tool if you want to retrieve the full content instead of a shortened version. 

    Args:
        file_ids (list[str]): A list of file ids to identify which attachments to read.
    Returns:
        str: A string representation of the full content of the attachments.
    '''
    client = bigquery.Client()
    file_ids_str = tuple(file_ids) if len(file_ids) > 1 else f"('{file_ids[0]}')"
    query = f"""SELECT file_id, content FROM vector_store.attachments WHERE file_id IN {file_ids_str}"""
    query_job = client.query(query)
    results = query_job.result()
    string_results = ""
    current_file_id = None
    for row in results:
        if not current_file_id or row.file_id != current_file_id:
            string_results += f"\n\n======== CONTENT FOR FILE_ID {row.file_id}: ========\n\n"
        current_file_id = row.file_id
        string_results += row.content
    return string_results



# ============================== 

TOOLS = [
    tavily_search,
    read_attachments,
    show_elements,
    list_attachments,
    query_project_attachments,
    query_laws,
    read_specific_law,
    #update_project,
    #clean_element,
]

BASELINE_TOOLS = [
    tavily_search,
]

BASELINE_RAG_TOOLS = [
    tavily_search,
    query_laws,
    read_specific_law,
    query_project_attachments,
    list_project_attachments,
    read_full_attachments,
]
