import os
from dotenv import load_dotenv
import json
from typing import Dict,TypedDict,List,Union,Annotated,Sequence,Optional, Literal, Tuple, Any
import logging
from pathlib import Path

from google.cloud import bigquery
from langchain_google_community import BigQueryVectorStore

from langchain_tavily import TavilySearch
from langchain_core.runnables import RunnableConfig
from langchain.tools import tool


from agent.agent_modules import AttachmentReader, VectorSearch


load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



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


tavily_search = TavilySearch(
    max_results=5,
    topic="general",
)

@tool
def read_vector_store(query: str, config : RunnableConfig ,  query_id : Optional[str] = None, file_id : Optional[str] = None) -> list[str]:
    '''Retrieve relevant chunks attachments from the vector store based on the query.
    All documents in current session are embedded to the vector store.

    Args:
        query (str): The user's query.
        session_id (str): The session ID to filter documents.
        query_id (Optional[str]): The query ID to filter documents.
        file_id (Optional[str]): The file ID to filter documents.
    '''
    user_id = config["configurable"].get("user_id", None)
    session_id = config["configurable"].get("session_id", None)
    vs = VectorSearch()
    vector_store = vs.init_vector_store(table_name="attachments")
    filters = {"user_id" : user_id,
               "session_id" :  session_id,
               "query_id" : query_id,
               "file_id" : file_id} 
    for k,v in filters.copy().items():
        if v is None or v == "":
            filters.pop(k)
    try:
        retriever = vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 4 ,
                                                                                        "filter" : filters})
        relevant_docs = retriever.invoke(query)
        return [doc.to_json() for doc in relevant_docs]
    except Exception as e:
        return []  # Return empty message on error


@tool
def read_attachment(file_id : str, config : RunnableConfig):
    '''
    Use this tool to read the content of an attachment stored in Google Cloud Storage.
    Args:
        file_id (str): The ID of the file to read.
        config (RunnableConfig): The runnable configuration containing user and session information.
    Returns:
        str: The content of the attachment as text.
    '''
    reader = AttachmentReader()
    user_id = config["configurable"].get("user_id", None)
    session_id = config["configurable"].get("session_id", None)
    return reader.read_attachment(session_id=session_id,
                                     user_id=user_id,
                                     file_id=file_id)

def analyze_doc(content : str) -> str:
    '''
    Analyze the content of a document and extract key information.
    Args:
        content (str): The content of the document to analyze.
    Returns:
        str: A message confirming that the data has been sent for analysis.
    '''
    return "Document content sent for analysis."

TOOLS = [
        tavily_search,
        list_table_info,
        run_query,
        read_vector_store,
        read_attachment,
      ]



PROMPT = """
You are CompanyAgent — a concise, capable business assistant that uses our internal BigQuery datasets (`agent.*`, `brreg.*` and `enin.*`) to answer precisely and act when needed.

Begin with a concise checklist (3–7 bullets) of what you will do; keep items conceptual, not implementation-level.

Events:

1. **User asks about a specific company:**
    - If the user has only provided the name for the company and not orgnr (`orgnr`), use the `get_org_num` tool to find it based on the company names. NB: Always search for multiple names!
    - If the user is uncertain of the name, use `tavily_search` to find possible company names based on query.
        - If `get_org_num` returns `match_type: "single"`, the tool has ALREADY fetched all company and industry data. Simply present the results directly - DO NOT call company_info again.
        - If `get_org_num` returns `match_type: "multiple"`, shortly make the user aware that they need to choose and wait for user selection.
        - If multiple matches are found, the options are automatically sent to the UI. Wait for the user to select the correct one.
    - 1. **User asks about a specific company:**
    ...
    - When the data is ready, simply **inform the user that the data is displayed** (it is sent automatically to UI). The content of your AIMessage **MUST** be minimal, e.g., "Data er lastet inn på dashbordet." DO NOT elaborate unless asked.

2. **User asks a general question about companies, industries, etc.:**
    - Understand the question and create the necessary query. If the question requires industry-level data, use the `get_nace_codes` tool to find relevant NACE codes (choose the most relevant ones).
    - Execute the query using `run_query`.
    - Present results compactly and informatively.
    - Clearly indicate status flags when relevant: bankrupt, under dissolution, forced liquidation, VAT registered.
    - Include location context (city/municipality) when helpful.

**Style:**
- Never guess. Ask clarifying questions if input is ambiguous.
- Do not make long elaborations unless specifically requested.

**Constraints:**
- Do not reveal internal implementation details or environment variables.

**General Tips:**
- When asked about an industry, use NACE codes to filter and aggregate data.
- If NACE code is unknown, find a well-known company in the industry to look up the code.
- Always use the database to answer. If the answer cannot be found, state so explicitly.
- If not specified, present results aggregated on a yearly basis.

**Most important columns from `agent.companies_all`:**
- `orgnr` (STRING)
- `name` (STRING)
- `employees_count` (FLOAT)
- `net_income` (FLOAT)
- `operating_profit` (FLOAT)
- `operating_revenue_total` (FLOAT)
- `assets_total` (FLOAT)
- `equity_total` (FLOAT)
- `liabilities_total` (FLOAT)
- `business_address_street` (STRING)
- `business_address_postal_code` (STRING)
- `business_address_municipality` (STRING)
- `nace1_description` (STRING)
- `nace1_code` (STRING)
- `accounting_period_from` (TIMESTAMP)
- `accounting_period_to` (TIMESTAMP)
- ...TRUNCATED. use `list_table_info` tool to explore more.
"""

