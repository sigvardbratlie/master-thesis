import streamlit as st
import pandas as pd
import json
import logging
from uuid import uuid4
from typing import Any, Optional
from ui.models import ToolResultEvent

logger = logging.getLogger(__name__)


def extract_valid_json(text: str) -> str:
    """Extract first valid JSON array from text"""
    text = text.strip()
    if not text.startswith('['):
        return text

    depth = 0
    in_string = False
    escape = False

    for i, char in enumerate(text):
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"' and not escape:
            in_string = not in_string
        if not in_string:
            if char == '[':
                depth += 1
            elif char == ']':
                depth -= 1
                if depth == 0:
                    return text[:i + 1]

    return text


def display_element(element: dict[str, Any], container):
    """Display chart/table element from display_data_on_ui tool"""
    with container:
        try:
            st.subheader(element.get("title"))

            # Parse dataframe
            try:
                df = pd.DataFrame(json.loads(element.get("dataframe_json")))
            except:
                data = extract_valid_json(element.get("dataframe_json"))
                df = pd.DataFrame(json.loads(data))

            x = element.get("x")
            y = element.get("y")
            chart_type = element.get("chart_type")

            # Render based on chart type
            if chart_type == "table":
                st.dataframe(df)
            elif chart_type == "bar":
                st.bar_chart(df, x=x, y=y)
            elif chart_type == "line":
                if x in df.columns:
                    df = df.set_index(x)
                st.line_chart(df, y=y)
            elif chart_type == "map":
                rename_lon = {"lng": "lon"}
                df = df.rename(columns=rename_lon).dropna(subset=["lat", "lon"])
                logger.debug(f'Dataframe columns: {df.columns} | len {len(df)} | NaN {df.isna().sum()} | head {df.head()}\n')
                st.map(df)
            elif chart_type == "scatter":
                st.scatter_chart(df, x=x, y=y)
            elif chart_type == "hist":
                data = df[x].value_counts()
                st.bar_chart(data)

        except Exception as e:
            st.error(f'Error displaying element: {e} | {element}')


def comp_button_widget(org_num_info: dict[str, Any], key_suffix: str = ""):
    """Display company selection button"""
    orgnr = org_num_info.get('orgnr')
    name = org_num_info.get('name')
    municipality = org_num_info.get('municipality')
    total_operating_income = str(f"{org_num_info.get('total_operating_income', 0):,}").replace(",", " ")
    currency = org_num_info.get('currency', 'NOK')

    button = st.button(
        f"{orgnr} ({name}, {municipality}, {total_operating_income} {currency})",
        key=f"org_num_btn_{orgnr}_{key_suffix}"
    )
    if button:
        st.session_state.question_to_process = (
            f"Gi meg informasjon om selskapet med organisasjonsnummer {orgnr}."
        )
        st.rerun()


def display_company_data(
    tool_data: Any,
    tool_name: str,
    container,
    query_id: str
):
    """Display company info with dashboard"""
    comp_json_str = None
    ind_json_str = None

    if tool_name == "company_info" and isinstance(tool_data, (list, tuple)) and len(tool_data) == 2:
        comp_json_str, ind_json_str = tool_data
    elif tool_name == "get_org_num" and tool_data.get("match_type") == "single":
        comp_json_str = tool_data.get("company_data", "")
        ind_json_str = tool_data.get("industry_data", "")

    if not comp_json_str:
        return

    try:
        comp_rows = json.loads(comp_json_str) if isinstance(comp_json_str, str) else comp_json_str
        df_company = pd.DataFrame(comp_rows) if isinstance(comp_rows, list) else pd.DataFrame()
    except Exception as e:
        st.error(f'Could not parse company data: {e}')
        return

    df_industry = pd.DataFrame()
    if ind_json_str:
        try:
            ind_rows = json.loads(ind_json_str) if isinstance(ind_json_str, str) else ind_json_str
            if isinstance(ind_rows, list):
                df_industry = pd.DataFrame(ind_rows)
        except Exception as e:
            st.warning(f'Could not parse industry data: {e}')

    if not df_company.empty:
        with container:
            st.session_state.company_data = comp_json_str
            st.session_state.industry_data = ind_json_str
            company_dashboard(df_company, industry_df=df_industry)
            st.page_link("pages/_company_dashboard.py", label="company dashboard")

            csv = df_company.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Last ned CSV",
                data=csv,
                file_name=f'company_data_{query_id}.csv',
                mime='text/csv',
                key=f'download_company_{query_id}_{str(uuid4())}'
            )


def handle_tool_result(
    event: ToolResultEvent,
    elements_container,
    company_data_container,
    show_sql_expander: bool = False,
    text_container = None
):
    """
    Unified handler for all tool results.

    Args:
        event: ToolResultEvent from backend
        elements_container: Container for charts/tables
        company_data_container: Container for company dashboards
        show_sql_expander: Whether to show SQL query expander (streaming mode)
        text_container: Optional container for displaying token_stream text
    """
    tool_name = event.tool_name
    tool_data = event.data
    tool_args = event.tool_args
    query_id = event.query_id

    # Display token stream if present (text that was shown during streaming)
    if event.token_stream and text_container:
        with text_container:
            st.markdown(event.token_stream)
            st.divider()

    # Handle different tool types
    if tool_name == "display_data_on_ui":
        display_element(tool_args, elements_container)

    elif tool_name == "get_org_num" and tool_data.get("match_type") == "multiple":
        choose_org = st.expander("Velg organisasjonsnummer", expanded=False)
        with choose_org:
            if tool_data.get("companies"):
                for idx, org_num_info in enumerate(tool_data["companies"]):
                    comp_button_widget(org_num_info, key_suffix=f"{query_id}_{idx}")
            else:
                st.info("Fant ingen selskaper som matcher navnet.")

    elif tool_name == "company_info" or (tool_name == "get_org_num" and tool_data.get("match_type") == "single"):
        display_company_data(tool_data, tool_name, company_data_container, query_id)

    elif tool_name == "run_query":
        try:
            with elements_container:
                try:
                    df = pd.DataFrame(tool_data)
                    st.dataframe(df)

                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Last ned CSV",
                        data=csv,
                        file_name=f'query_result_{query_id}.csv',
                        mime='text/csv',
                        key=f'download_query_{query_id}_{str(uuid4())}'
                    )
                except Exception as e:
                    st.json(tool_data)
                    st.error(f'Kunne ikke parse data til tabell: {e}')
        except Exception as e:
            st.error(f'Error displaying query result: {e}')

        if show_sql_expander and tool_args:
            with st.expander("Se SQL-spørring", expanded=False):
                st.code(tool_args.get("sql_query", ""), language="sql")
