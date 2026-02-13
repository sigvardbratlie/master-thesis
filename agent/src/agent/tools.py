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
def list_table_info(table_id : str,dataset_id : str) -> str:
    """
    Lists the schema information for the specified BigQuery table.
    Use this tool to understand the structure of the tables you are querying.

    Args:
        table_id (str): The table id
        dataset_id (str): The dataset id 

    Example
    list_table_info with query {'table_id': 'companies_all', 'dataset_id': 'agent'}
    
    """
    client = bigquery.Client()
    table = client.get_table(f"{dataset_id}.{table_id}")
    schema_info = [{"name": field.name, "type": field.field_type, "mode": field.mode} for field in table.schema]
    return json.dumps(schema_info, indent=2)   
@tool
def run_query(sql_query: str) -> dict:
    """
    Executes a SQL query against the BigQuery datasets and returns the results as a dictionary.
    Primary use the `agent` dataset and `company_all table`.
    When querying with NACE codes, always use the `LIKE` operator.
    Args:
        sql_query (str): The SQL query to execute. Always use the `LIKE` operator when filtering on text columns.
    Returns:
        dict: The query results as a dictionary.

    Example:
    run_query with query 
        SELECT 
            org_number, 
            name,
            SUM(operating_revenue_total) AS operating_revenue_total
        FROM agent.companies_all 
        WHERE nace1_code LIKE '%64%' 
            GROUP BY org_number, name
            ORDER BY operating_revenue_total DESC 
            LIMIT 10;
    """
    client = bigquery.Client()
    query_job = client.query(sql_query)
    try:
        results = query_job.result().to_dataframe()
        return results.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return {"error": str(e)}

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
def read_project_vectorstore(query:  str, 
                             project_id: str,
                             k: int = 5
                             ) -> str:
    '''Function to read from the vectorstore of a specific project. 
    Use when you want to query the vectorstore directly for information retrieval (RAG).
    
    Args:
        query (str): The query to search in the vectorstore.
        project_id (str): The project id to identify which vectorstore to query.
        k (int): The number of top results to retrieve from the vectorstore. Default is 5.
    Returns:
        str: The retrieved information from the vectorstore based on the query.
    '''
    vectorstore = BQVectorStore()
    results = vectorstore.query(query=query, collection_id=project_id, k=k)
    if not results:
        return f"No relevant information found in the vectorstore for project {project_id}."
    retrieved_content = "\n".join([f"- {doc.page_content}" for doc in results])
    return f"Retrieved information from vectorstore for project {project_id}:\n{retrieved_content}"

@tool
def update_project(project_id: str,):
    '''Use this function to trigger an update of the projects state to include the conversations current information'''
    return f"Project {project_id} has been sent for update"

def clean_element(element_type : Literal["events", "parties", "title", "background", "claims", "deadlines", "damages", "disputed_facts", "undisputed_facts"], project_id):
    '''Use this function to trigger a cleaning of a specific element in the projects state. 
    For example, if you want to clean the vectorstore of the project, use element_type 'vectorstore'.'''
    return f"Element {element_type} in project {project_id} has been sent for cleaning"

TOOLS = [
        tavily_search,
        #list_table_info,
        #run_query,
        read_attachment,
      ]
