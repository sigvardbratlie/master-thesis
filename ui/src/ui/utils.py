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
    st.session_state.setdefault("user_first_name", None)
    st.session_state.setdefault("user_last_name", None)
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
    st.session_state.setdefault('attachment_cache', {})
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

    st.session_state.setdefault("clear_input_counter", 0)

    apply_global_styles()


def apply_global_styles():
    """Inject global CSS styles matching the pill/rounded design."""
    st.markdown("""
        <style>
        /* Rounded buttons everywhere */
        button {
            border-radius: 2rem !important;
        }

        /* Rounded expanders */
        [data-testid="stExpander"] {
            border-radius: 1rem !important;
            overflow: hidden;
        }
        [data-testid="stExpander"] details {
            border-radius: 1rem !important;
        }
        [data-testid="stExpander"] summary {
            border-radius: 1rem !important;
        }

        /* Rounded selectboxes */
        [data-testid="stSelectbox"] > div > div {
            border-radius: 1rem !important;
        }

        /* Rounded text inputs */
        [data-testid="stTextInput"] > div > div > input {
            border-radius: 1rem !important;
        }

        /* Rounded text areas */
        [data-testid="stTextArea"] textarea {
            border-radius: 1rem !important;
        }

        /* Rounded file uploader */
        [data-testid="stFileUploader"] > div {
            border-radius: 1rem !important;
        }

        /* Rounded info/warning/error/success boxes */
        [data-testid="stAlert"] {
            border-radius: 1rem !important;
        }

        /* Rounded popover */
        [data-testid="stPopover"] > button {
            border-radius: 2rem !important;
        }

        /* Rounded radio pills */
        [data-testid="stRadio"] label > div {
            border-radius: 2rem !important;
        }

        /* Rounded chat input */
        [data-testid="stChatInput"] {
            border-radius: 1.5rem !important;
        }
        [data-testid="stChatInput"] textarea {
            border-radius: 1.5rem !important;
        }

        /* Rounded status containers */
        [data-testid="stStatusWidget"] {
            border-radius: 1rem !important;
        }
        </style>
    """, unsafe_allow_html=True)


@st.cache_resource
def get_resource(resource):
    """Generic cached resource loader"""
    return resource() 