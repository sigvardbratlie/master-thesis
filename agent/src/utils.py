import os
import re
from typing import Literal,List
from google.cloud import bigquery
from langchain_tavily import TavilySearch
import requests
import pandas as pd
from langchain.tools import tool
from dotenv import load_dotenv
import json
from typing import Dict,TypedDict,List,Union,Annotated,Sequence,Optional, Literal, Tuple, Any
from google.cloud import bigquery,storage
import os
import logging
from langchain_google_vertexai.embeddings import VertexAIEmbeddings
from langchain_google_community import BigQueryVectorStore
from datetime import datetime
from langchain_core.runnables import RunnableConfig
from src.agent_modules import AttachmentReader, VectorSearch


load_dotenv()
project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




def get_company(orgnr: str) -> str:
    query = f"""
    WITH fin AS (
  SELECT
    f.organisasjonsnummer                          AS org_number,
    EXTRACT(YEAR FROM f.regnskapsperiode_tilDato)  AS accounting_year,
    f.regnskapsperiode_tilDato                     AS period_end,
    f.valuta                                     AS currency,

    -- Resultatregnskap
    f.resultatregnskapResultat_aarsresultat AS net_profit,
    f.resultatregnskapResultat_ordinaertResultatFoerSkattekostnad AS profit_before_tax,
    f.resultatregnskapResultat_driftsresultat_driftsinntekter_sumDriftsinntekter AS total_operating_income,
    f.resultatregnskapResultat_driftsresultat_driftskostnad_sumDriftskostnad AS total_operating_expenses,
    f.resultatregnskapResultat_driftsresultat_driftsresultat AS operating_profit,
    f.resultatregnskapResultat_finansresultat_nettoFinans AS net_financial_income,
    f.resultatregnskapResultat_finansresultat_finansinntekt_sumFinansinntekter AS total_financial_income,
    f.resultatregnskapResultat_finansresultat_finanskostnad_sumFinanskostnad AS total_financial_expenses,

    -- Balanse
    f.egenkapitalGjeld_sumEgenkapitalGjeld AS total_equity_and_liabilities,
    f.egenkapitalGjeld_egenkapital_opptjentEgenkapital_sumOpptjentEgenkapital AS retained_earnings,
    f.egenkapitalGjeld_egenkapital_innskuttEgenkapital_sumInnskuttEgenkaptial AS contributed_equity,
    f.eiendeler_sumEiendeler AS total_assets,
    f.eiendeler_omloepsmidler_sumOmloepsmidler AS current_assets,
    f.eiendeler_anleggsmidler_sumAnleggsmidler AS non_current_assets
  FROM `company-data-455309.brreg.financial` f
),
fin_one_per_year AS (
  SELECT * EXCEPT(rn)
  FROM (
    SELECT
      f.*,
      ROW_NUMBER() OVER (
        PARTITION BY org_number, accounting_year
        ORDER BY period_end DESC
      ) AS rn
    FROM fin f
  )
  WHERE rn = 1
  AND accounting_year < EXTRACT(YEAR FROM CURRENT_DATE())
),
companies AS (
  SELECT DISTINCT
    c.organisasjonsnummer AS org_number,
    c.navn AS name,
    c.registrertIMvaregisteret AS vat_registered,
    c.registrertIStiftelsesregisteret AS registered_in_foundation_register,
    c.stiftelsesdato AS incorporation_date,
    c.organisasjonsform_beskrivelse AS legal_form,
    c.naeringskode1_kode AS nace1_code,
    c.naeringskode1_beskrivelse AS nace1_description,
    c.antallAnsatte AS employees_count,
    c.konkurs AS bankrupt,
    c.underAvvikling AS under_dissolution,
    c.underTvangsavviklingEllerTvangsopplosning AS forced_liquidation,
    c.forretningsadresse_land AS business_address_country,
    c.forretningsadresse_kommune AS business_address_municipality,
    c.forretningsadresse_kommunenummer AS business_address_municipality_number,
    c.forretningsadresse_adresse AS business_address_street,
    c.forretningsadresse_postnummer AS business_address_postal_code,
    c.forretningsadresse_poststed AS business_address_city
  FROM `brreg.companies` c
),
roles AS (
  SELECT
    d.org_number,
    ARRAY_AGG(
      STRUCT(
        d.first_name,
        d.last_name,
        d.date_of_birth,
        d.role_description
      )
      ORDER BY d.role_description, d.last_name, d.first_name, d.date_of_birth
    ) AS roles
  FROM (
    SELECT DISTINCT
      r.organisasjonsnummer AS org_number,
      r.person_navn_fornavn AS first_name,
      r.person_navn_etternavn AS last_name,
      r.person_fodselsdato AS date_of_birth,
      r.type_beskrivelse AS role_description
    FROM `brreg.roles` r
  ) d
  GROUP BY d.org_number
)
SELECT
  f.accounting_year,
  f.currency,

  -- Finans
  f.net_profit,
  f.profit_before_tax,
  f.total_operating_income,
  f.total_operating_expenses,
  f.operating_profit,
  f.net_financial_income,
  f.total_financial_income,
  f.total_financial_expenses,
  f.total_equity_and_liabilities,
  f.retained_earnings,
  f.contributed_equity,
  f.total_assets,
  f.current_assets,
  f.non_current_assets,

  -- Selskap
  c.org_number,
  c.name,
  c.vat_registered,
  c.registered_in_foundation_register,
  c.incorporation_date,
  c.legal_form,
  c.nace1_code,
  c.nace1_description,
  c.employees_count,
  c.bankrupt,
  c.under_dissolution,
  c.forced_liquidation,
  c.business_address_country,
  c.business_address_municipality,
  c.business_address_municipality_number,
  c.business_address_street,
  c.business_address_postal_code,
  c.business_address_city,

  -- Roller som array
  r.roles
FROM fin_one_per_year f
LEFT JOIN companies c USING (org_number)
LEFT JOIN roles r USING (org_number)
WHERE c.org_number = "{orgnr}"
ORDER BY f.accounting_year DESC;
    """
    try:
        client = bigquery.Client()
        result = client.query(query).result().to_dataframe()
        if result.empty:
            return f"No data found for organization number {orgnr}."
        return result.to_json(orient="records", force_ascii=False)

    except Exception as e:
        logger.error(f'Error initializing BigQuery client: {e}')
        return f"Error initializing BigQuery client: {e}"

def get_industry_data(orgnr: str) -> str:
    query = f"""
WITH target AS (
  SELECT DISTINCT c.naeringskode1_kode AS nace1_code
  FROM `brreg.companies` c
  WHERE c.organisasjonsnummer = "{orgnr}"
),

company_pool AS (
  SELECT DISTINCT
    c.organisasjonsnummer AS org_number,
    c.navn AS name,
    c.naeringskode1_kode AS nace1_code,
    c.naeringskode1_beskrivelse AS nace1_description,
    c.antallAnsatte AS employees_count,
    c.konkurs AS bankrupt,
    c.underAvvikling AS under_dissolution,
    c.underTvangsavviklingEllerTvangsopplosning AS forced_liquidation,
    c.forretningsadresse_kommune AS business_address_municipality,
    c.forretningsadresse_poststed AS business_address_city
  FROM `brreg.companies` c
  JOIN target t
    ON c.naeringskode1_kode = t.nace1_code
),

fin AS (
  SELECT
    f.organisasjonsnummer AS org_number,
    EXTRACT(YEAR FROM f.regnskapsperiode_tilDato) AS accounting_year,
    CAST(f.regnskapsperiode_tilDato AS DATE) AS period_end_date,
    f.valuta AS currency,
    f.resultatregnskapResultat_aarsresultat AS net_profit,
    f.resultatregnskapResultat_ordinaertResultatFoerSkattekostnad AS profit_before_tax,
    f.resultatregnskapResultat_driftsresultat_driftsinntekter_sumDriftsinntekter AS total_operating_income,
    f.resultatregnskapResultat_driftsresultat_driftskostnad_sumDriftskostnad AS total_operating_expenses,
    f.resultatregnskapResultat_driftsresultat_driftsresultat AS operating_profit,
    f.resultatregnskapResultat_finansresultat_nettoFinans AS net_financial_income,
    f.resultatregnskapResultat_finansresultat_finansinntekt_sumFinansinntekter AS total_financial_income,
    f.resultatregnskapResultat_finansresultat_finanskostnad_sumFinanskostnad AS total_financial_expenses,
    f.egenkapitalGjeld_sumEgenkapitalGjeld AS total_equity_and_liabilities,
    f.egenkapitalGjeld_egenkapital_opptjentEgenkapital_sumOpptjentEgenkapital AS retained_earnings,
    f.egenkapitalGjeld_egenkapital_innskuttEgenkapital_sumInnskuttEgenkaptial AS contributed_equity,
    f.eiendeler_sumEiendeler AS total_assets,
    f.eiendeler_omloepsmidler_sumOmloepsmidler AS current_assets,
    f.eiendeler_anleggsmidler_sumAnleggsmidler AS non_current_assets
  FROM `company-data-455309.brreg.financial` f
  JOIN company_pool p
    ON p.org_number = f.organisasjonsnummer
),

-- 4) Én rad per selskap per år (siste rapport i året)
fin_one_per_year AS (
  SELECT * EXCEPT(rn)
  FROM (
    SELECT
      f.*,
      ROW_NUMBER() OVER (
        PARTITION BY org_number, accounting_year
        ORDER BY period_end_date DESC
      ) AS rn
    FROM fin f
  )
  WHERE rn = 1
  AND accounting_year < EXTRACT(YEAR FROM CURRENT_DATE())
),

-- 5) JOIN med FX ved å finne siste kurs ≤ periode
fx_joined AS (
  SELECT
    f.org_number,
    f.accounting_year,
    f.period_end_date,
    f.currency,
    fx.rates AS rate_to_nok,
    ROW_NUMBER() OVER (
      PARTITION BY f.org_number, f.accounting_year, f.period_end_date
      ORDER BY fx.date DESC
    ) AS rn
  FROM fin_one_per_year f
  LEFT JOIN `admin.FX` fx
    ON fx.code = f.currency
   AND fx.date <= f.period_end_date
),

-- 6) Behold kun siste kurs (rn=1)
fx_asof AS (
  SELECT org_number, accounting_year, period_end_date, currency, rate_to_nok
  FROM fx_joined
  WHERE rn = 1
  AND accounting_year < EXTRACT(YEAR FROM CURRENT_DATE())
),

-- 7) Konverter til NOK
fin_nok AS (
  SELECT
    f.*,
    IF(f.currency = 'NOK', 1.0, x.rate_to_nok) AS fx_rate_to_nok,
    CASE WHEN f.currency = 'NOK' THEN f.net_profit
         WHEN x.rate_to_nok IS NULL THEN NULL
         ELSE f.net_profit * x.rate_to_nok END AS net_profit_nok,
    CASE WHEN f.currency = 'NOK' THEN f.profit_before_tax
         WHEN x.rate_to_nok IS NULL THEN NULL
         ELSE f.profit_before_tax * x.rate_to_nok END AS profit_before_tax_nok,
    CASE WHEN f.currency = 'NOK' THEN f.total_operating_income
         WHEN x.rate_to_nok IS NULL THEN NULL
         ELSE f.total_operating_income * x.rate_to_nok END AS total_operating_income_nok,
    CASE WHEN f.currency = 'NOK' THEN f.operating_profit
         WHEN x.rate_to_nok IS NULL THEN NULL
         ELSE f.operating_profit * x.rate_to_nok END AS operating_profit_nok,
    CASE WHEN f.currency = 'NOK' THEN f.total_assets
         WHEN x.rate_to_nok IS NULL THEN NULL
         ELSE f.total_assets * x.rate_to_nok END AS total_assets_nok
  FROM fin_one_per_year f
  LEFT JOIN fx_asof x
    USING (org_number, accounting_year, period_end_date, currency)
)

-- 8) Aggreger per NACE og år (i NOK)
SELECT
  p.nace1_code,
  p.nace1_description,
  n.accounting_year,
  AVG(n.net_profit_nok)             AS avg_net_profit_nok,
  AVG(n.profit_before_tax_nok)      AS avg_profit_before_tax_nok,
  AVG(n.total_operating_income_nok) AS avg_total_operating_income_nok,
  AVG(n.operating_profit_nok)       AS avg_operating_profit_nok,
  AVG(n.total_assets_nok)           AS avg_total_assets_nok,
  AVG(p.employees_count)            AS avg_employee_count,
  COUNT(*)                          AS company_count
FROM fin_nok n
JOIN company_pool p USING (org_number)
GROUP BY p.nace1_code, p.nace1_description, n.accounting_year
ORDER BY n.accounting_year DESC;

    """
    try:
        client = bigquery.Client()
        result = client.query(query).result().to_dataframe()
        if result.empty:
            return f"No industry data found for organization number {orgnr}."
        return result.to_json(orient="records", force_ascii=False)

    except Exception as e:
        logger.error(f'Error initializing BigQuery client: {e}')
        return f"Error initializing BigQuery client: {e}"


@tool
def company_info(orgnr: str) -> str:
    """
    Use this tool to get detailed information about a specific company identified by its organization number (orgnr).
    **NB: The data is sent to UI, so do not elaborate in the response! Just confirm that data is sent to UI.**
    Args:
        orgnr (str): The organization number of the company.
    Returns:
        str: A JSON string containing the company information.
    """
    return get_company(orgnr),get_industry_data(orgnr)

@tool
def display_data_on_ui(dataframe_json: str ,title: str,chart_type: Literal["line", "bar", "table", "map","scatter","hist"], x: str = None, y : List[str] = None) -> str:
    """
    Use this tool to visualize data for the user in the user interface.
    It takes a dataframe in JSON format, a chart type, and a title.
    The user interface will handle the actual rendering of the plot or table.
    Only use this tool when you have data ready to be shown.

    Args:
        dataframe_json (str): The dataframe in JSON format.
        title (str): The title of the plot
        chart_type (Literal["line", "bar", "table", "map","scatter","hist"]): The type of chart to use.
        x (str): The column to use for the x-axis.
        y (List[str]): The columns to use for the y-axis.

    For dataframes containing any kind of time variable, choose 'line' and make sure to specify the correct columns for x and y corresponding to the datafrmae.
    Example:
        display_data_on_ui with query {'title': 'Gjennomsnittlig pris per kvm i Langhus senter det siste året',
                                            'chart_type': 'line',
                                            "x" : "month",
                                            "y" : "average_sqm_price"
                                            'dataframe_json': '[{"month":"2024-10","average_sqm_price":62631.58},{"month":"2024-11","average_sqm_price":63297.87},{"month":"2024-12","average_sqm_price":45187.35},
                                            {"month":"2025-01","average_sqm_price":85000.0},{"month":"2025-03","average_sqm_price":74528.3},
                                            {"month":"2025-04","average_sqm_price":71764.71},{"month":"2025-05","average_sqm_price":63994.09},{"month":"2025-06","average_sqm_price":54131.65},
                                            {"month":"2025-07","average_sqm_price":65509.44},{"month":"2025-08","average_sqm_price":70482.99},{"month":"2025-09","average_sqm_price":43750.0}]',
                                            }
    If chart_type is 'hist', the x value to be of the feature of interest, and leave y to be None.


    Otherwise, use your best judgement to choose the correct chart type.

    NB: Remember Column names are in english while user query can be in any language! make sure that column names in x, y and data corresponds!
    """
    return f"Data has been sent to the UI for display as a {chart_type} with title '{title}', x = {x}, y = {y}."


@tool
def get_org_num(company_names: list[str]) -> list[str]:
    """
    Use this tool to get the organization number (orgnr) for a company based on its name.
    
    IMPORTANT: 
    - If only ONE match is found, this tool AUTOMATICALLY fetches complete company 
      and industry data. You do NOT need to call company_info afterwards.
    - If multiple matches are found, returns a list for user selection.
    
    Args:
        company_names (list[str]): The names of the companies to look up. i.e query: 'Aker BP AS' -> ['aker bp as', 'aker bp', 'aker'] or for query: 'DNB bank AS' -> ['dnb', 'dnb bank']
    
    Returns:
        dict: Either {"match_type": "single", "orgnr": "...", "company_data": {...}, "industry_data": {...}}
              or {"match_type": "multiple", "count": X, "companies": [...]}
    """
    company_names = [name.lower() for name in company_names]
    client = bigquery.Client()

    query = '''
    SELECT 
        c.organisasjonsnummer AS orgnr,
        c.navn AS name,
        c.forretningsadresse_kommune AS municipality,
        f.resultatregnskapResultat_driftsresultat_driftsinntekter_sumDriftsinntekter AS total_operating_income,
        f.valuta AS currency
    FROM brreg.companies c
    JOIN (SELECT * FROM brreg.financial WHERE EXTRACT(YEAR FROM regnskapsperiode_fraDato) = 2024) f ON c.organisasjonsnummer = f.organisasjonsnummer
    WHERE EXISTS (
        SELECT 1
        FROM UNNEST(@company_names) AS name
        WHERE LOWER(navn) LIKE CONCAT('%', name, '%')
    )
    ORDER BY 
        f.resultatregnskapResultat_driftsresultat_driftsinntekter_sumDriftsinntekter DESC,
        f.eiendeler_sumEiendeler  DESC
    LIMIT 30
    '''

    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("company_names", "STRING", company_names)
            ]
        )
    )
    results = job.result().to_dataframe().to_dict(orient="records")
    if len(results) == 1:
        orgnr = results[0]["orgnr"]
        logger.info(f"Single company match found: {orgnr}. Fetching detailed info...")
        company_data, industry_data = company_info.invoke({"orgnr": orgnr})
        return {
            "match_type": "single",
            "orgnr": orgnr,
            "company_data": company_data,
            "industry_data": industry_data
        }
    
    # Hvis flere selskaper, returner listen
    return {
        "match_type": "multiple",
        "count": len(results),
        "companies": results
    }


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
def find_nace(query : str,):
    '''
    Use this tool to find the most relevant NACE code(s) for a given business description.
    
    Args:
        query (str): A description of the business activities.
    Returns:
        list: A list of relevant NACE codes with descriptions.
    
    '''
    embedding = VertexAIEmbeddings(model_name="text-embedding-005")

    PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
    REGION = "europe-west1"
    DATASET = "vector_store"
    TABLE = "nace"

    vector_store = BigQueryVectorStore(
        project_id=PROJECT_ID,
        dataset_name=DATASET,
        table_name=TABLE,
        location=REGION,
        embedding=embedding,
    )
    retriever = vector_store.as_retriever(search_kwargs={"k": 3,
                                                     "filter" : "level = 3"},
                                      )
    results = retriever.invoke(query)
    return [doc.model_dump_json() for doc in results]


def fetch_exchange_rates():
    """
    Henter årsavslutningskurser (31.12) for USD, EUR, GBP mot NOK fra Norges Bank API.
    """
    current_year = datetime.today().year
    start_year = 2000
    url = "https://data.norges-bank.no/api/data/EXR/B.USD+EUR+GBP.NOK.SP"
    headers = {"Accept": "application/vnd.sdmx.data+json;version=1.0.0"}

    # Hent hele perioden i ett kall
    params = {
        "startPeriod": f"{start_year}-01-01",
        "endPeriod": f"{current_year}-12-31",
        "locale": "no"
    }

    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Feil {response.status_code}: {response.text}")

    data = response.json()
    series = data["data"]["dataSets"][0]["series"]
    currencies = data["data"]["structure"]["dimensions"]["series"][1]["values"]
    dates = [x["id"] for x in data["data"]["structure"]["dimensions"]["observation"][0]["values"]]

    records = []
    for i, cur in enumerate(currencies):
        key = f"0:{i}:0:0"
        observations = series[key]["observations"]
        for idx, obs in observations.items():
            date_str = dates[int(idx)]
            if date_str.endswith("-12-31"):  # behold bare 31.12
                records.append({
                    "code": cur["id"],
                    "date": date_str,
                    "rates": float(obs[0])
                })

    df = pd.DataFrame(records)
    print(f"Hentet {len(df)} observasjoner:")
    print(df.head())
    return df
def write_to_bigquery(df):
    """
    Laster data inn i BigQuery-tabellen admin.FX
    """
    client = bigquery.Client()
    dataset = "admin"
    table_id = "FX"

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # endre til WRITE_TRUNCATE om du vil overskrive
    )

    table_ref = client.dataset(dataset).table(table_id)
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()
    print(f"✅ Lastet opp {job.output_rows} rader til {dataset}.{table_id}")
#@tool
def update_FX_rates() -> str:
    """
    Use this tool to update the foreign exchange rates in the BigQuery admin.FX table.
    This tool fetches the latest exchange rates from Norges Bank and updates the table accordingly.
    """
    data = fetch_exchange_rates()
    write_to_bigquery(data)
    return "Foreign exchange rates updated successfully."



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

COMPANY_TOOLS = [
                company_info,
                 get_org_num,
                 display_data_on_ui,
                 tavily_search,
                 list_table_info,
                 run_query,
                 find_nace,
                 read_vector_store,
                 read_attachment,
                ]
