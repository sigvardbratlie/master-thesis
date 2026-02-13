import os
from dotenv import load_dotenv
import json
from typing import Optional, Literal
import logging

from google.cloud import bigquery

from langchain_tavily import TavilySearch
from langchain_core.runnables import RunnableConfig
from langchain.tools import tool

from database import SupabaseStorageManager, DocumentProcessor, BQVectorStore


load_dotenv()
logging.basicConfig(level=logging.INFO)
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
logger = logging.getLogger(__name__)

tavily_search = TavilySearch(
    max_results=5,
    topic="general",
)

@tool
def read_attachment(path : str, 
                    #config : RunnableConfig
                    ) -> str:
    '''
    Reads and processes an attachment from Supabase storage based on the provided path.
    Use only when the attachment content is not provided in the conversation history.

    Args:
        path (str): The path to the attachment in Supabase storage.
    
    Returns:
        str: Processed content of the attachment.
    '''
    storage_manager = SupabaseStorageManager()
    document_processor = DocumentProcessor()
    content = storage_manager.read_attachment(path=path)
    try:
        file_id = path.split("/")[-1].split(".")[0] if "." in path else path.split("/")[-1]
        ext = path.split(".")[-1] if "." in path else ""
    except Exception as e:
        logger.error(f"Error extracting file_id and extension from path: {e}")
        return None
    if ext in ["pdf", "docx", "pptx", "eml", "txt", "md"]:
        file_type = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "eml": "message/rfc822",
            "txt": "text/plain",
            "md": "text/markdown"
        }.get(ext, "text/plain")
        docs = document_processor.parse(content=content,
                                        metadata = {"file_id": file_id, 
                                                    "session_id": None,
                                                    "embedding_model": None},  
                                        file_type=file_type,)
        content_txt = document_processor.to_plain_text(docs)
        return f"Content for file path {path}: \n{content_txt}\n\n"
    else:
        logger.error(f"Unsupported file extension: {ext}")
        return []

@tool
def read_project_attachments(query:  str, 
                             project_id: str,
                             k: int = 5
                             ) -> str:
    '''Function to use RAG to retrieve documents of a specific project.
    
    Args:
        query (str): The query to search in the vectorstore.
        project_id (str): The project id to identify which vectorstore to query.
        k (int): The number of top results to retrieve from the vectorstore. Default is 5.
    Returns:
        str: The retrieved information from the vectorstore based on the query.
    '''
    vectorstore = BQVectorStore()
    results = vectorstore.query(query=query, collection_id="attachments", k=k, filter = {"project_id": project_id})
    if not results:
        return f"No relevant information found in the vectorstore for project {project_id}."
    res = "=== Retrieved relevant chunks from vectorstore: ===\n"
    for doc in results:
        res += f'filename: {doc.metadata.get("filename", "Unknown")}' \
        f'title: {doc.metadata.get("title", "Unknown")} | ' \
        f'path: {doc.metadata.get("path", "Unknown")} | ' \
        f'| chunk: {doc.metadata.get("chunk", "Unknown")} of {doc.metadata.get("total_chunks", "Unknown")} total chunks\n'
        res += f"{doc.page_content}\n\n"
    return res

@tool
def read_laws(query: str, k: int = 5) -> str:
    '''Function to use RAG to retrieve relevant laws based on a query.
    
    Args:
        query (str): The query to search in the vectorstore.
        k (int): The number of top results to retrieve from the vectorstore. Default is 5.
    Returns:
        str: The retrieved information from the vectorstore based on the query.
    '''
    vectorstore = BQVectorStore()
    query = '''Jeg kjøpt en elektrisk sparkesykkel som ikke fungerer og virker farlig å kjøpe på. 
    Hva skal jeg gjøre? Hva er mine frister og rettigheter?'''
    k = 5
    results = vectorstore.query(query=query, collection_id="laws", k=k)
    if not results:
        return "No relevant laws found in the vectorstore."
    res = "=== Retrieved relevant laws from vectorstore: ===\n"
    for doc in results:
        res += f'Title {doc.metadata.get("title", "Unknown")} | Paragraph {doc.metadata.get("paragraph_number", "Unknown")} |Legal area: {doc.metadata.get("legal_area", "Unknown")}\n'
        res += f"{doc.page_content}\n\n"
    return res

@tool
def update_project(project_id: str,):
    '''Use this function to trigger an update of the projects state to include the conversations current information'''
    return f"Project {project_id} has been sent for update"

@tool
def clean_element(element_type : Literal["events", "parties", "title", "background", "claims", "deadlines", "damages", "disputed_facts", "undisputed_facts"], project_id: str):
    '''Use this function to trigger a cleaning of a specific element in the projects state. 
    For example, if you want to clean the vectorstore of the project, use element_type 'vectorstore'.'''
    return f"Element {element_type} in project {project_id} has been sent for cleaning"

TOOLS = [
        tavily_search,
        read_attachment,
        read_project_attachments,
        read_laws,
        update_project,
        clean_element,
      ]
