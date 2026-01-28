import streamlit as st
import logging

# Import auth functions
from ui.services.auth_service import (
    is_logged_in,
    restore_session,
    render_login_form,
    save_token_to_url
)

# Import services
#from ui.services.session_service import SessionService
from ui.database.database_modules import SupabaseManager

# Import UI components
from ui.ui_components.renders import render_first_question, render_sidebar, display_history, handle_new_question

# Import utils
from ui.utils import init_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(page_title="Company Agent", layout="wide")
init_state()

# ================== AUTH ==================

restore_session()

# ================== MAIN APP LOGIC ==================

if is_logged_in():
    # Save token to URL (in case it was refreshed)
    save_token_to_url()

    # Create session service
    # session_service = SessionService(
    #     backend_url=st.session_state.backend_url,
    #     user_id=st.session_state.user_id,
    #     access_token=st.session_state.access_token
    # )
    supabase_manager = SupabaseManager()

    # Render sidebar
    render_sidebar(supabase_manager)

    # Main content
    if st.session_state.first_question:
        render_first_question()
    else:
        display_history()
        handle_new_question(supabase_manager)

else:
    # Login screen
    render_login_form()

st.json(st.session_state, expanded=False)