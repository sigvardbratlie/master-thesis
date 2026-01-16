from uuid import uuid4
import streamlit as st
import os
import logging

# Import services
from ui.services.auth_service import AuthService
from ui.services.session_service import SessionService

# Import UI components
from ui.ui_components.renders import render_first_question,render_sidebar,display_history, handle_new_question

# Import utils
from ui.utils import init_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Page configuration
st.set_page_config(page_title="Company Agent", layout="wide")
init_state()

st.markdown("<style>.status-box{opacity:.85}</style>", unsafe_allow_html=True)

# ================== MAIN APP LOGIC ==================
#st.json(st.session_state, expanded=False)

if st.user.is_logged_in:
    # Authenticate with backend
    auth_service = AuthService(backend_url=st.session_state.backend_url)
    if not auth_service.authenticate_with_backend():
        st.error("Authentication failed")
        st.stop()

    # Create session service
    session_service = SessionService(
        backend_url=st.session_state.backend_url,
        user_id=st.session_state.user_id,
        access_token=st.session_state.access_token
    )

    # Render sidebar
    render_sidebar(session_service)



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
