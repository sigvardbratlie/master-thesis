import os
import streamlit as st
import uuid
import logging

logger = logging.getLogger(__name__)
logger.setLevel("DEBUG")

# Backend URL configuration
LOCAL = True
backend_url = "http://0.0.0.0:8080" if LOCAL else None

@st.cache_data(show_spinner=False)
def log_init():
    logger.info(f'======= RUNNING WITH BACKEND URL {backend_url} LOCAL {LOCAL}')

log_init()




def init_state():
    """Initialize Streamlit session state with default values"""
    st.session_state.setdefault("state_initialized", True)
    st.session_state.setdefault("is_authenticated", False)

    # User info
    st.session_state.setdefault("user_id", None)
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("project_id", None)
    st.session_state.setdefault("session_title", None)

    # Messages & history
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("first_question", True)

    # Agent config
    st.session_state.setdefault("llm_model", None)

    # UI state
    st.session_state.setdefault("question_to_process", None)
    st.session_state.setdefault("files_to_process", [])
    st.session_state.setdefault("sessions_loaded", False)
    st.session_state.setdefault("current_session_loaded", False)
    st.session_state.setdefault("valuation_doc_count", 0)
    st.session_state.setdefault("is_searching", False)

    # Backend & auth
    st.session_state.setdefault("access_token", None)
    st.session_state.setdefault("token_type", None)
    st.session_state.setdefault("backend_url", backend_url)

    # Tool results
    st.session_state.setdefault("tool_results", {})
    st.session_state.setdefault("factsheet", None)
    st.session_state.setdefault("attachments", [])
    st.session_state.setdefault("project_data", [])

    st.session_state.setdefault("supabase_client", None)

@st.cache_resource
def get_resource(resource):
    """Generic cached resource loader"""
    return resource() 