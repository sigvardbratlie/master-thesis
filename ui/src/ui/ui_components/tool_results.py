import streamlit as st
import pandas as pd
import json
import logging
from uuid import uuid4
from typing import Any, Optional
from ui.models import *

logger = logging.getLogger(__name__)

class ToolResultComponent:
    """Component to handle and display tool results in the UI"""

    def __init__(self):
        pass

    def extract_valid_json(self, text: str) -> str:
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


    def display_element(self, element: dict[str, Any], container):
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


    def handle_tool_result(self, 
        event: StreamEvent,
        elements_container,
        show_sql_expander: bool = False,
        text_container = None
    ):
        """
        Unified handler for all tool results.

        Args:
            event: ToolResultEvent from backend
            elements_container: Container for charts/tables
            show_sql_expander: Whether to show SQL query expander (streaming mode)
            text_container: Optional container for displaying token_stream text
        """
        tool_name = event.data.tool_name
        tool_data = event.data.data
        tool_args = event.data.tool_args
        query_id = event.query_id

        # # Display token stream if present (text that was shown during streaming)
        # if event.token_stream and text_container:
        #     with text_container:
        #         st.markdown(event.token_stream)
        #         st.divider()

        # Handle different tool types
        if tool_name == "display_data_on_ui":
            self.display_element(tool_args, elements_container)

        elif tool_name == "read_vector_store":
            pass
        elif tool_name == "read_attachment":
            pass
        elif tool_name == "tavily_search":
            with elements_container:
                st.markdown(f"Searched {tool_args.get('query', '')}, found {len(tool_data)} results.")

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

@st.cache_resource
def get_tool_result_component() -> ToolResultComponent:
    """Get cached ToolResultComponent instance"""
    return ToolResultComponent()