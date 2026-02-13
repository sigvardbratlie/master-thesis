import streamlit as st
import logging


from ui.services.auth_service import SupabaseAuthService
from ui.services import get_supabase_auth_service
from ui.ui_components import get_chat_component, get_sidebar_component
from ui.ui_components.attachments import get_attachment_component
from ui.utils import init_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
init_state()

chat_component = get_chat_component()
sidebar_component = get_sidebar_component()
attachment_component = get_attachment_component()
auth_service = get_supabase_auth_service()

st.set_page_config(page_title="Agent", page_icon="⚖️", layout="wide")


# ================== AUTH ==================
auth_service.restore_session()

# ================== MAIN APP LOGIC ==================

if auth_service.is_logged_in():
    auth_service.save_token_to_url()
    
    # Render attachment dialog if one is selected
    attachment_component.render_attachment_dialog()

    with st.sidebar:
        sidebar_component.render_sidebar()

    # Main content
    if st.session_state.first_question:
        chat_component.render_first_question()
    else:
        chat_component.display_history()
        chat_component.handle_new_question()

else:
    # Login screen
    auth_service.render_login_form()

st.json(st.session_state, expanded=False)

st.json(st.session_state.get("messages", []), expanded=False)