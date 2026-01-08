from uuid import uuid4
import streamlit as st
import json
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
import os
import logging

# Import models
from models import AskAgentRequest, ToolResultEvent

# Import services
from services.auth_service import AuthService
from services.session_service import SessionService
from services.streaming_service import StreamingService

# Import UI components
from ui_components.renders import render_first_question, render_chat_input,render_sidebar
from ui_components.tool_results import handle_tool_result
from ui_components.attachments import mk_attachment_payload, view_uploaded_file, view_attachment

# Import utils
from utils import init_state, load_custom_css

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Page configuration
st.set_page_config(page_title="Company Agent", layout="wide")
init_state()
load_custom_css()

st.markdown("<style>.status-box{opacity:.85}</style>", unsafe_allow_html=True)


def display_history():
    """Display chat history with all messages"""
    # Group messages by query cycle (each human message starts a new cycle)
    cycles = []
    current_cycle = []
    for msg in st.session_state.messages:
        if msg.get("type") == "human":
            if current_cycle:
                cycles.append(current_cycle)
            current_cycle = [msg]
        else:
            current_cycle.append(msg)
    if current_cycle:
        cycles.append(current_cycle)

    # Display each cycle
    for cycle in cycles:
        # Display user message
        user_msg = next((m for m in cycle if m.get("type") == "human"), None)
        if user_msg:
            with st.chat_message("user"):
                st.markdown(user_msg.get("data", {}).get("content", ""))
                attachments = user_msg.get("data", {}).get("attachments", [])
                for att in attachments:
                    if att:
                        view_attachment(att)

        # Prepare containers for this cycle
        with st.chat_message("assistant"):
            details_expander = st.expander("Detaljer", expanded=False)
            elements_container = st.container()
            company_data_container = st.container()
            text_container = st.container()

            # Collect details for expander
            tool_calls_msgs = []
            sql_queries = []

            for msg in cycle:
                if msg.get("type") == "ai" and msg.get("data", {}).get("tool_calls"):
                    tool_calls_msgs.append(msg)
                elif msg.get("type") == "tool_result" and msg.get("tool_args"):
                    sql_queries.append(msg)

            # Display details in expander
            if tool_calls_msgs or sql_queries:
                with details_expander:
                    for ai_msg in tool_calls_msgs:
                        for tool_call in ai_msg.get("data").get("tool_calls", []):
                            if tool_call.get("name"):
                                st.markdown(f"**Verktøy kalt:** {tool_call.get('name')}")
                                st.markdown("**Argumenter:**")
                                st.json(tool_call.get("args", {}))
                                st.divider()

                    for sql_msg in sql_queries:
                        if sql_msg.get("tool_name") == "run_query":
                            st.markdown("**SQL-spørring:**")
                            st.code(sql_msg.get("tool_args", {}).get("sql_query", ""), language="sql")
                            st.divider()

            # Display tool results
            for msg in cycle:
                if msg.get("type") == "tool_result":
                    try:
                        tool_event = ToolResultEvent(**msg)
                        handle_tool_result(
                            tool_event,
                            elements_container,
                            company_data_container,
                            show_sql_expander=False,
                            text_container=text_container
                        )
                    except Exception as e:
                        logger.error(f"Error handling tool result in history: {e}")

            # Display final answer
            for msg in cycle:
                if msg.get("type") == "ai":
                    data = msg.get("data", {})
                    token_stream_displayed = data.get("token_stream", "")
                    if token_stream_displayed:
                        with text_container:
                            st.markdown(token_stream_displayed)
                            st.divider()


def handle_new_question():
    """Handle new question input and streaming response"""
    question_to_process = st.session_state.question_to_process
    chat_question = render_chat_input()

    question = chat_question if not question_to_process else question_to_process
    st.session_state.question_to_process = None

    if question:
        query_id = str(uuid4())

        # Prepare attachment payload
        attachment_payload = []
        for file in question.files if hasattr(question, "files") else []:
            attachment = mk_attachment_payload(file)
            if attachment:
                attachment_payload.append(attachment)

        # Add user message to session
        user_msg = {
            "type": "human",
            "data": {
                "content": question.text if hasattr(question, "text") else question,
                "attachments": [att.model_dump() for att in attachment_payload]
            }
        }
        st.session_state.messages.append(user_msg)

        # Display user message
        with st.chat_message("user"):
            st.markdown(question.text if hasattr(question, "text") else question)

            if hasattr(question, "files") and question.files:
                files = question.files
                for f in files:
                    view_uploaded_file(f)

        # Display assistant response
        with st.chat_message("assistant"):
            answer_container = st.container()
            with answer_container:
                elements_container = st.container()
                company_data_container = st.container()
                details_expander = st.expander("Detaljer", expanded=False)
                text_container = st.container()
                status_container = st.container()

            status_placeholder = status_container.empty()
            status_box = status_placeholder.status("🧠 Jobber med saken...", expanded=False)

            # Prepare request
            request = AskAgentRequest(
                question=question.text if hasattr(question, "text") else question,
                session_id=st.session_state.session_id,
                attachments=attachment_payload,
                query_id=query_id,
                agent_type=st.session_state.agent_type,
                llm_provider=st.session_state.llm_provider,
                domain=st.session_state.domain
            )

            # Create streaming service
            streaming_service = StreamingService(
                st.session_state.backend_url,
                st.session_state.access_token
            )

            # Define callbacks
            def on_tool_result(event: ToolResultEvent):
                handle_tool_result(
                    event,
                    elements_container,
                    company_data_container,
                    show_sql_expander=True,
                    text_container=text_container
                )

            def status_callback(label: str, state: str):
                status_box.update(label=label, state=state)

            # Stream response
            try:
                with text_container:
                    st.write_stream(streaming_service.stream_response(
                        request=request,
                        on_tool_result=on_tool_result,
                        status_callback=status_callback
                    ))
            except Exception as e:
                st.error(f"Streaming error: {e}")
                logger.error(f"Streaming error: {e}")
            finally:
                st.session_state.is_searching = False

            # Reload session title if needed
            if not st.session_state.session_title or st.session_state.session_title == "Ny samtale":
                st.cache_data.clear()
                session_service = SessionService(
                    st.session_state.backend_url,
                    st.session_state.user_id
                )
                response = session_service.load_session_history(st.session_state.session_id)
                if response:
                    st.session_state.session_title = response.title
                    st.session_state.messages = response.events
                    st.rerun()


# ================== MAIN APP LOGIC ==================

if st.user.is_logged_in:
    # Authenticate with backend
    auth_service = AuthService(st.session_state.backend_url)
    if not auth_service.authenticate_with_backend():
        st.error("Authentication failed")
        st.stop()

    # Create session service
    session_service = SessionService(
        st.session_state.backend_url,
        st.session_state.user_id
    )

    # Render sidebar
    render_sidebar(session_service)

    # main, right = st.columns([4, 1])
    # with main:
    # Main content
    if st.session_state.first_question:
        render_first_question()
    else:
        display_history()
        handle_new_question()

else:
    # Login screen
    st.markdown("**Vennligst logg inn for å fortsette!**")
    if st.button("Logg inn"):
        st.login("google")

# Debug info
st.json(st.session_state.messages, expanded=False)
