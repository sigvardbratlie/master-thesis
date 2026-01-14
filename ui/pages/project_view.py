import streamlit as st
from ui.utils import init_state
import math
from typing import Optional
from ui.models import AskAgentRequest, AttachmentModel
from ui.services.streaming_service import StreamingService
from ui.services.session_service import SessionService
from ui.services.auth_service import AuthService
from ui.ui_components.renders import render_first_question, handle_new_question, display_history
from ui.ui_components.attachments import mk_attachment_payload
import uuid
import requests
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_state()

# ================== AUTHENTICATION ==================

if not st.user.is_logged_in:
    st.warning("Please log in to access this page.")
    st.stop()

# Authenticate with backend
auth_service = AuthService(backend_url=st.session_state.backend_url)
if not auth_service.authenticate_with_backend():
    st.error("Authentication failed")
    st.stop()

# ================== MAIN PAGE ==================



streaming_service = StreamingService(
                    st.session_state.backend_url,
                    st.session_state.access_token
                )
session_service = SessionService(
                    backend_url=st.session_state.backend_url,
                    user_id=st.session_state.user_id,
                    access_token=st.session_state.access_token
                )

def on_project_select(project : dict):
    st.session_state.session_id = None
    st.session_state.project_id = project['project_id']
    st.session_state.session_title = project.get('session_title', None)
    logger.info(f"Selected project: {st.session_state.project_id}")

    # Load the factsheet for the selected project
    project_data = session_service.load_project()
    #st.json(project_data)
    if project_data:
        st.session_state.factsheet = project_data.get('factsheet')
        st.session_state.attachments = project_data.get('attachments', [])
        logger.info(f"Loaded factsheet for project: {st.session_state.project_id}")
    else:
        st.session_state.factsheet = None
        st.session_state.attachments = []
        logger.warning(f"No factsheet found for project: {st.session_state.project_id}")

    #st.rerun()

def render_select_projects():
    st.header("Select Project")
    projects = session_service.load_projects()
    if projects:
        with st.expander("Projects", expanded=True):
            for project in projects:
                st.button(f"Project ID: {project['project_id']} - {project.get('session_title', 'No Title')}", on_click=lambda p=project: on_project_select(p))
                # if st.button(f"Project ID: {project['project_id']} - {project.get('session_title', 'No Title')}", on_click=lambda p=project: on_project_select(p)):
                #     st.session_state.session_id = None
                #     st.session_state.project_id = project['project_id']
                #     st.session_state.session_title = project.get('session_title', None)
                #     logger.info(f"Selected project: {st.session_state.project_id}")

                #     # Load the factsheet for the selected project
                #     project_data = session_service.load_project()
                #     st.json(project_data)
                #     if project_data:
                #         st.session_state.factsheet = project_data.get('factsheet')
                #         st.session_state.attachments = project_data.get('attachments', [])
                #         logger.info(f"Loaded factsheet for project: {st.session_state.project_id}")
                #     else:
                #         st.session_state.factsheet = None
                #         st.session_state.attachments = []
                #         logger.warning(f"No factsheet found for project: {st.session_state.project_id}")

                #     st.rerun()
    else:
        st.info("No projects found. Please initialize a new project.")

def render_selected_project():
    factsheet = st.session_state.get('factsheet', {})
    st.header("Selected Project:")
    st.markdown(f"### {factsheet.get('title')}")
    st.markdown(f'Parties')
    st.markdown(f'- **Plaintiff**: {", ".join([p["legal_name"] for p in factsheet.get("parties", []) if p.get("role") == "plaintiff"])}')
    st.markdown(f'- **Defendant**: {", ".join([p["legal_name"] for p in factsheet.get("parties", []) if p.get("role") == "defendant"])}')
    
    with st.expander("Timeline", expanded=False, icon="🕒"):
        timeline = factsheet.get('timeline', [])
        sorted_timeline = sorted(timeline, key=lambda x: x.get('date', ''))
        for event in sorted_timeline:
            st.markdown(f"**{event.get('date', 'No Date')}**: {event.get('description', 'No Description')}")

    with st.expander("Governing Law", expanded=False,icon="⚖️"):
        governing_law = factsheet.get('governing_law', {})
        for k,v in governing_law.items():
            if v:
                st.markdown(f"  - **{k.replace('_',' ').title()}**: {v}")

    with st.expander("Claims", expanded=False, icon="📄"):
        claims = factsheet.get('claims', [])
        for i, claim in enumerate(claims, start=1):
            st.markdown(f"**Claim {i}**")
            for k,v in claim.items():
                if v:
                    st.markdown(f"  - **{k.replace('_',' ').title()}**: {v}")

    with st.expander("Damages", expanded=False, icon="💰"):
        damages = factsheet.get('damages', [])
        for i, damage in enumerate(damages, start=1):
            st.markdown(f"**Damage {i}**")
            for k,v in damage.items():
                if v:
                    st.markdown(f"  - **{k.replace('_',' ').title()}**: {v}")

    with st.expander("Deadlines", expanded=False, icon="⏰"):
        deadlines = factsheet.get('deadlines', [])
        for i, deadline in enumerate(deadlines, start=1):
            st.markdown(f"**Deadline {i}**")
            for k,v in deadline.items():
                if v:
                    st.markdown(f"  - **{k.replace('_',' ').title()}**: {v}")

    with st.expander("Attachments Overview", expanded=False, icon="📎"):
        for file in st.session_state.get('attachments', []):
            st.markdown(f"- **{file.get('filename', 'No Filename')}** ({file.get('category', 'No Category')}, {file.get('significance', 'No Significance')})")

    with st.expander("Background", expanded=False, icon="📚"):
        background = factsheet.get('background', 'No background information available.')
        st.markdown(background)

def render_project_sessions():
    st.header("Project Sessions")
    sessions = session_service.load_project_sessions()
    if sessions:
        for session in sessions:
            st.markdown(f"- **Session ID**: {session.session_id}, **Title**: {session.session_title}, **Last Updated**: {session.last_updated}")
    else:
        st.info("No sessions found for this project.")

with st.sidebar:
    new_project = st.button("Initialize New Project", icon="🆕")
    if new_project:
        st.session_state.clear()
        st.rerun()

    st.divider()
    render_select_projects()
    st.divider()
    if st.session_state.get('project_id', None):
        render_project_sessions()
        st.divider()
        render_selected_project()



if not st.session_state.project_id:
    st.title("Project View Page")
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
                    try:
                        factsheet = response.json()
                    except Exception as e:
                        logger.error(f"Error parsing factsheet JSON: {str(e)}")
                        factsheet = {}
                    st.session_state.project_data = factsheet
                    st.rerun()
                else:
                    st.error(f"Error initializing project: {response.text}")
                    logger.error(f"Error initializing project: {response.status_code} - {response.text}")
            except Exception as e:
                st.error(f"Exception during project initialization: {str(e)}")
                logger.exception("Exception during project initialization")

else:
    #st.success(f"Project ID: {st.session_state.project_id} is initialized.")
    #st.markdown("You can now start asking questions related to your project in the chat interface.")

    # Load factsheet if not already in session state
    if 'project_data' not in st.session_state or st.session_state.project_data is None:
        logger.info(f"Loading project data for project: {st.session_state.project_id}")
        project_data = session_service.load_project()
        if project_data:
            st.session_state.factsheet = project_data.get('factsheet')
            st.session_state.attachments = project_data.get('attachments', [])
        else:
            st.warning("Could not load factsheet or attachments for this project.")
            st.session_state.factsheet = None
            st.session_state.attachments = []
    # Display factsheet if available
    if st.session_state.factsheet:
        if st.session_state.first_question:
            render_first_question()
        else:
            display_history()
            handle_new_question()
    else:
        st.warning("No factsheet available for this project.")


