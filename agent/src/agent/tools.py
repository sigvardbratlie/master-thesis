from importlib.resources import path
import os
import re
from dotenv import load_dotenv
import json
from typing import Optional, Literal
import logging

from google.cloud import bigquery

from langchain_tavily import TavilySearch
from langchain_core.runnables import RunnableConfig
from langchain.tools import tool

from database import SupabaseStorageManager, BQVectorStore, SupabaseManager
from documents import DocumentProcessor


load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
logger = logging.getLogger(__name__)

tavily_search = TavilySearch(
    max_results=5,
    topic="general",
)

@tool
def read_attachments(
    file_ids: list[str],
    # config : RunnableConfig
) -> str:
    """
    Reads and processes multiple attachments from Supabase storage based on the provided paths.

    Args:
        file_ids (str): The file IDs of the attachments in Supabase storage. 

    Returns:
        str: Processed content of the attachment.
    """
    db = SupabaseManager()
    storage_manager = SupabaseStorageManager()
    document_processor = DocumentProcessor()
    paths = db.get_paths(file_ids)
    contents = storage_manager.read_attachments(paths=paths)
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
            docs = document_processor.parse(
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
            content_txt = document_processor.to_plain_text(docs)
            return f"CONTENT FOR FILEPATH {path}: \n\n{content_txt}\n\n"
        else:
            logger.error(f"Unsupported file extension: {ext}")
            return []

    results = "Results for reading attachments:" + "\n" + "-" * 50 + "\n\n"
    for path, content in contents.items():
        if content is not None:
            results += process_attachment(path, content)
            results += "\n" + "-" * 50 + "\n\n"
        else:
            results += f"Can not find any contents for {path}\n"
            results += "\n" + "-" * 50 + "\n\n"
    return results

@tool
def query_project_attachments(query: str, project_id: str, k: int = 5, metadata : dict = None) -> str:
    """Function to use RAG to retrieve documents of a specific project.

    Args:
        query (str): The query to search in the vectorstore.
        project_id (str): The project id to identify which vectorstore to query.
        k (int): The number of top results to retrieve from the vectorstore. Default is 5.
        metadata (dict, optional): Additional metadata to filter the vectorstore query. Defaults to None. I.e., {'file_id' : '741ef083-9335-4a55-bbe1-ea866bf01758'}.
    Returns:
        str: The retrieved information from the vectorstore based on the query.

    Available metadata fields are : file_id, filename, file_type (MIME)
    """
    filters = {"project_id": project_id}
    if metadata:
        filters.update(metadata)
    vectorstore = BQVectorStore()
    results = vectorstore.query(query=query, collection_id="attachments", k=k, filters=filters)
    if not results:
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
def show_elements(element_types : list[Literal["events", "parties", "claims", "damages",]],
                  project_id: str,
                  significance: list[Literal["high", "medium", "low"]] = None,
                  ):
    """Use this function to retrieve structured case facts (parties, events, claims, damages) from the factsheet.
    Only request the element types relevant to the question. Do not fetch all types unless the question explicitly requires all of them.
    Args:
        element_types (list[Literal["events", "parties", "claims", "damages",]]): A list of the element types to show. Only include types needed to answer the question. For example, a question about actors → ["parties"]; about timeline → ["events"].
        significance (list[Literal["high", "medium", "low"]], optional): A list of significance levels to filter the elements. Defaults to None.
        project_id (str): The project id to identify which project to retrieve the elements from.
    Returns:
        str: A string representation of the requested elements.
    """
    sm = SupabaseManager()
    factsheet = sm.load_factsheet(project_id=project_id)
    if not factsheet:
        return f"No project {project_id}"
    value = f"=== List of project elements: {', '.join(element_types)} ===\n\n"
    all_fields =[ "events", "parties", "claims", "damages", "deadlines", "background"]
    excluded_fields = [e for e in all_fields if e not in element_types]
    if excluded_fields:
        value += factsheet.shorten_factsheet(
                        significance=significance,
                        excluded_fields=excluded_fields,)
    return value

@tool
def list_attachments(element_types : list[Literal["attachments", "emails"]],
                  project_id: str,
                  significance: list[Literal["high", "medium", "low"]] = None,
                  ):
    """Use this function to retrieve a list of the projects files and emails.
    Args:
        element_types (list[Literal["attachments", "emails"]]): A list of the element types to show. For example, if you only want to show attachments and emails, use ["attachments", "emails"].
        significance (list[Literal["high", "medium", "low"]], optional): A list of significance levels to filter the elements. Defaults to None.
        project_id (str): The project id to identify which project to retrieve the elements from.
    Returns:
        str: A string representation of the requested elements.
    """
    sm = SupabaseManager()
    project= sm.load_project(project_id=project_id)
    if not project:
        return f"No project {project_id}"
    value = f"=== List of project elements: {', '.join(element_types)} ===\n\n"

    value += project.shorten_attachments(
                    significance=significance,
                    excluded_keys=["description",] if "attachments" in element_types else None,)
    value += project.shorten_emails(
                    significance=significance,
                    excluded_keys=["description",] if "emails" in element_types else None,)
    return value

@tool
def list_project_attachments(project_id: str) -> str:
    '''Use this function to retrieve a list of the projects attachments with their file_ids. 
    
    Args:
        project_id (str): The project id to identify which project's attachments to list.
    Returns:
        str: A string representation of the list of attachments with their file_ids.
    '''
    client = bigquery.Client()
    query = f"""SELECT filename, file_id FROM vector_store.attachments WHERE project_id = '{project_id}'"""
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
    query = f"""SELECT file_id, content FROM vector_store.attachments WHERE file_id IN {tuple(file_ids)}"""
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
