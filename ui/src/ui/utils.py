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
    st.session_state.setdefault("agent_type", "fast")
    st.session_state.setdefault("llm_provider", "openai")

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


# @st.cache_data(show_spinner=False)
# def load_custom_css():
#     """Load custom CSS file if it exists"""
#     base_dir = os.path.dirname(os.path.abspath(__file__))
#     css_file_path = os.path.join(base_dir, ".streamlit", "style.css")

#     if os.path.exists(css_file_path):
#         with open(css_file_path) as f:
#             st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
#     else:
#         st.error(
#             f"Style not loaded! Looking for {css_file_path}. "
#             f"CWD={os.getcwd()}, Dir={os.listdir(base_dir)}."
#         )
