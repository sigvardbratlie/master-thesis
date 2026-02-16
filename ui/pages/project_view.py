import streamlit as st
import math
from typing import Optional,Literal

from ui.models import AskAgentRequest, AttachmentModel
from ui.ui_components import get_attachment_component, get_chat_component, get_sidebar_component, get_project_component, get_tool_result_component
from ui.services import get_streaming_service, get_supabase_manager, get_supabase_auth_service
from ui.utils import init_state,get_resource

import uuid
import requests
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_state()





project_component = get_project_component()
backend_service = get_supabase_manager()
chat_component = get_chat_component()
sidebar_component = get_sidebar_component()
auth_service = get_supabase_auth_service()
attachment_component = get_attachment_component()

# ================== AUTH ==================
auth_service.restore_session()

# ================== MAIN APP LOGIC ==================

if auth_service.is_logged_in():
    # Render attachment dialog if one is selected
    attachment_component.render_attachment_dialog()

    #st.json(st.session_state.factsheet)
    if st.session_state.session_id is None:
        st.session_state.session_id = str(uuid.uuid4())

        
    with st.sidebar:
        project_component.run_sidebar()
        st.divider()
        sidebar_component.llm_model_options(default_choice=3,expanded=True)


    if not st.session_state.project_id:
        st.html("<div style='font-size: 3.5rem; line-height: 1;'>📁</div>")
        st.title("Project View", anchor=False)
        ""  # Spacer
        with st.container():
            project_component.render_new_project_input()

    else:
        # Load factsheet if not already in session state
        if not st.session_state.get('factsheet'):
            logger.info(f"Loading project data for project: {st.session_state.project_id}")

            # First check if we have project_data from init response
            if st.session_state.get('project_data'):
                st.session_state.factsheet = st.session_state.project_data.get('factsheet')
                st.session_state.attachments = st.session_state.project_data.get('attachments', [])
            else:
                # Load from Firestore
                project_data = backend_service.load_project(project_id=st.session_state.project_id)
                if project_data:
                    st.session_state.factsheet = project_data.get('factsheet')
                    st.session_state.attachments = project_data.get('attachments', [])
                else:
                    st.warning("Could not load factsheet or attachments for this project.")
                    st.session_state.factsheet = None
                    st.session_state.attachments = []

        # Display factsheet if available
        if st.session_state.get('factsheet'):
            if "update_project_view" in st.session_state and st.session_state.update_project_view:
                cols = st.columns(2)
                with cols[0]:
                    st.markdown(f'New input')
                    project_component.render_new_project_input(mode = "update")
                with cols[1]:
                    project_component.render_selected_project(factsheet=st.session_state.factsheet,)
            else:
                if st.session_state.first_question:
                    chat_component.render_first_question()
                else:
                    chat_component.display_history()
                    chat_component.handle_new_question()
        else:
            st.warning("No factsheet available for this project.")
else:
    # Login screen
    auth_service.render_login_form()

st.json(st.session_state.factsheet, expanded=False)