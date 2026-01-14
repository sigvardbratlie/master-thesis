import streamlit as st
from ui.utils import init_state
import math
from typing import Optional
from ui.models import AskAgentRequest, AttachmentModel
from ui.services.streaming_service import StreamingService
from ui.services.session_service import SessionService
from ui.ui_components.attachments import mk_attachment_payload
import uuid
import requests
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_state()



#def init_project_view_page():
st.title("Project View Page")

streaming_service = StreamingService(
                    st.session_state.backend_url,
                    st.session_state.access_token
                )
#st.info(st.session_state.access_token)
session_service = SessionService(
                    backend_url=st.session_state.backend_url,
                    user_id=st.session_state.user_id,
                    access_token=st.session_state.access_token
                )
st.info(st.session_state.access_token)

with st.sidebar:
    st.header("Select Project")
    projects = session_service.load_projects()
    if projects:
        with st.expander("Projects", expanded=True):
            for project in projects:
                if st.button(f"Project ID: {project['project_id']} - {project.get('session_title', 'No Title')}"):
                    st.session_state.project_id = project['project_id']
                    st.session_state.session_title = project.get('session_title', None)
                    st.session_state.domain = project.get('domain', 'legal')
                    logger.info(f"Selected project: {st.session_state.project_id}")
                    st.rerun()
    else:
        st.info("No projects found. Please initialize a new project.")
    


if not st.session_state.project_id:
    with st.container():
        user_input = st.text_area("Project details", 
                              placeholder="Describe your project here...",
                              help="Provide details about your project to initialize it.",
                              height=150)  # Starthøyde

        
        # Bruk CSS for å gjøre file uploader større
        st.markdown("""
            <style>
            [data-testid="stFileUploader"] {
                padding: 3rem 1rem !important;
            }
            [data-testid="stFileUploader"] section {
                min-height: 300px !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        user_files = st.file_uploader("Upload project files:", 
                                    accept_multiple_files=True, 
                                    type=["txt", "csv", "xlsx", "pdf"],
                                    help="You can upload multiple files.")
        attachments = [mk_attachment_payload(f) for f in user_files] if user_files else []
        
        
        query_id = str(uuid.uuid4())
        project_id = str(uuid.uuid4())
        

        payload = AskAgentRequest(
            question=user_input,
            attachments=attachments,
            session_id=st.session_state.session_id,
            domain = st.session_state.domain,
            query_id=query_id,
            agent_type=st.session_state.agent_type,
            llm_provider=st.session_state.llm_provider,
            project_id=project_id
        )

        

        init_project = st.button("Initialize Project", icon="🚀")
        if init_project:
            st.session_state.project_id = project_id
            try:
                response = streaming_service.init_project(payload)
                if response.status_code == 200:
                    st.success("Project initialized successfully!")
                    logger.info(f"Project initialized: {response.json()}")
                    factsheet = response.json()
                    st.session_state.factsheet = factsheet
                    st.rerun()
                else:
                    st.error(f"Error initializing project: {response.text}")
                    logger.error(f"Error initializing project: {response.status_code} - {response.text}")
            except Exception as e:
                st.error(f"Exception during project initialization: {str(e)}")
                logger.exception("Exception during project initialization")

else:
    st.success(f"Project ID: {st.session_state.project_id} is initialized.")
    st.markdown("You can now start asking questions related to your project in the chat interface.")

    st.json(st.session_state.factsheet)


