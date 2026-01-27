import streamlit as st
from ui.utils import init_state
import math
from typing import Optional,Literal
from ui.models import AskAgentRequest, AttachmentModel
from ui.services.streaming_service import StreamingService
from ui.services.session_service import SessionService
from ui.services.auth_service import *
from ui.ui_components.renders import render_first_question, handle_new_question, display_history, llm_model_options
from ui.ui_components.attachments import mk_attachment_payload, view_attachment
import uuid
import requests
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_state()
if st.session_state.session_id is None:
    st.session_state.session_id = str(uuid.uuid4())


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
    # Preserve auth credentials before clearing
    user_id = st.session_state.get('user_id')
    user_name = st.session_state.get('user_name')
    access_token = st.session_state.get('access_token')
    refresh_token = st.session_state.get('refresh_token')
    auth_initialized = st.session_state.get('_auth_initialized')
    backend_url = st.session_state.get('backend_url')

    st.session_state.clear()
    init_state()

    # Restore auth credentials
    st.session_state.user_id = user_id
    st.session_state.user_name = user_name
    st.session_state.access_token = access_token
    st.session_state.refresh_token = refresh_token
    st.session_state._auth_initialized = auth_initialized
    st.session_state.backend_url = backend_url

    st.session_state.project_id = project['project_id']
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
                st.button(f"{project.get('title', 'No Title')}", 
                          on_click=lambda p=project: on_project_select(p), 
                          key = project.get('project_id','no-id'))
                
    else:
        st.info("No projects found. Please initialize a new project.")

def display_field(label,value, icon,factsheet):
    with st.expander(label.title(), expanded=False, icon=icon):
        content = factsheet.get(value, []) if factsheet.get(value) else []
        for i, item in enumerate(content, start=1):
            st.markdown(f"**{label.title()} {i}**")
            if isinstance(item, dict):
                for k,v in item.items():
                    if v:
                        st.markdown(f"  - **{k.replace('_',' ').title()}**: {v}")
            elif isinstance(item, list):
                for sub_item in item:
                    st.markdown(f"  - {sub_item}")
            elif isinstance(item, str):
                st.markdown(f"  - {item}")
            else:
                st.markdown(f"  - {str(item)}")


def render_selected_project():
    factsheet = st.session_state.get('factsheet', {})
    st.header("Selected Project:")
    st.markdown(f"### {factsheet.get('title')}")
    
    with st.expander("Timeline", expanded=False, icon="🕒"):
        timeline = factsheet.get('timeline', [])
        sorted_timeline = sorted(timeline, key=lambda x: x.get('event_date', ''))   
        for event in sorted_timeline:
            st.markdown(f"**{event.get('event_date', 'No Date')}**: {event.get('description', 'No Description')}")
    
    elements = {"parties" : "👥", "governing_law" : "⚖️", "claims" : "📄", "damages" : "💰", "deadlines" : "⏰",}
    for field, icon in elements.items():
        display_field(label = field.replace("_"," ").title(), value = field, icon = icon, factsheet=factsheet)
    
    with st.expander("Background", expanded=False, icon="📚"):
        st.markdown(factsheet.get("background", ""))
    

    with st.expander("Attachments Overview", expanded=False, icon="📎"):
        for file in st.session_state.get('attachments', []):
            view_attachment(file)
            #
            # if st.button(f"- **{file.get('filename', 'No Filename')}** ({file.get('category', 'No Category')}, {file.get('significance', 'No Significance')})", key=file.get('file_id','no-id')):
            #     st.pdf()

def render_project_sessions():
    #st.header("Project Sessions")
    sessions = session_service.load_project_sessions()
    if sessions:
        for session in sessions:
            session_selected = st.button(f"- **Session ID**: {session.session_id}, **Title**: {session.title if session.title else 'No Title'}")
            if session_selected:
                history = session_service.load_session_history(session.session_id)
                #st.info(history)
                st.session_state.messages = history.events
                st.session_state.session_id = session.session_id
                st.session_state.session_title = session.title
                st.session_state.first_question = None
                logger.info(f"Selected session: {st.session_state.session_id}")
                st.rerun()
    else:
        st.info("No sessions found for this project.")

def render_new_input(mode : Literal["update","init"] = "init"):
    
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
    
    query_id = str(uuid.uuid4()) 
    project_id = st.session_state.project_id if st.session_state.project_id else str(uuid.uuid4())

    user_files = st.file_uploader("Upload project files:", 
                                accept_multiple_files=True, 
                                type=["txt", "csv", "xlsx", "pdf"],
                                help="You can upload multiple files.")
    attachments = [mk_attachment_payload(f,query_id=query_id) for f in user_files] if user_files else []
    
    payload = AskAgentRequest(
        question=user_input,
        attachments=attachments,
        session_id=st.session_state.session_id,
        query_id=query_id,
        llm_model=st.session_state.llm_model,
        project_id=project_id
    )

    
    init_project = st.button("Initialize Project", icon="🚀") if mode == "init" else st.button("Update Project", icon="🚀")
    if init_project:
        st.session_state.project_id = project_id

        # Spinner container
        spinner_placeholder = st.empty()

        # Custom animated spinner with rotating text
        spinner_html = """
        <style>
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        @keyframes fade {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
        }
        .spinner-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 2rem;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 12px;
            margin: 1rem 0;
        }
        .racket-spinner {
            font-size: 3rem;
            animation: spin 1.5s linear infinite;
            margin-bottom: 1rem;
        }
        .text-container {
            overflow: hidden;
            height: 30px;
        }
        .rotating-text {
            animation: slide 10s steps(5) infinite;
        }
        @keyframes slide {
            0% { transform: translateY(0); }
            100% { transform: translateY(-150px); }
        }
        .rotating-text span {
            display: block;
            height: 30px;
            line-height: 30px;
            color: #00d4ff;
            font-weight: 500;
            font-size: 1.1rem;
        }
        </style>

        <div class="spinner-container">
            <div class="racket-spinner">🏸</div>
            <div class="text-container">
                <div class="rotating-text">
                    <span>📄 Scanning documents...</span>
                    <span>🔍 Analyzing content...</span>
                    <span>📋 Extracting key information...</span>
                    <span>📊 Building factsheet...</span>
                    <span>🚀 Initializing project...</span>
                </div>
            </div>
        </div>
        """

        spinner_placeholder.markdown(spinner_html, unsafe_allow_html=True)

        try:
            response = streaming_service.init_project(payload) if mode == "init" else streaming_service.update_project(payload)

            # Clear spinner
            spinner_placeholder.empty()

            if response.status_code == 200:
                st.success("Project initialized successfully!")
                logger.info(f"Project initialized: {response.json()}")
                try:
                    project_data = response.json()
                except Exception as e:
                    logger.error(f"Error parsing factsheet JSON: {str(e)}")
                    project_data = {}

                # Set factsheet and attachments from response
                st.session_state.project_data = project_data
                st.session_state.factsheet = project_data.get('factsheet')
                st.session_state.attachments = project_data.get('attachments', [])

                st.session_state.update_project_view = True

                st.rerun()
            else:
                spinner_placeholder.empty()
                st.error(f"Error initializing project: {response.text}")
                logger.error(f"Error initializing project: {response.status_code} - {response.text}")
        except Exception as e:
            spinner_placeholder.empty()
            st.error(f"Exception during project initialization: {str(e)}")
            logger.exception("Exception during project initialization")



with st.sidebar:
    new_project = st.button("Initialize New Project", icon="🆕")
    if new_project:
        st.session_state.clear()
        init_state()
        st.rerun()

    st.divider()
    render_select_projects()
    st.divider()
    if st.session_state.get('project_id', None):
        with st.expander("Project Sessions", expanded=True):
            render_project_sessions()
            #st.divider()
            if st.button("New session", icon="💬"):
                project_id = st.session_state.project_id
                st.session_state.clear()
                init_state()
                st.session_state.project_id = project_id
                logger.info(f"Initialized new session: {st.session_state.session_id}")
                st.rerun()
        st.divider()
        if st.session_state.get('factsheet', None):
            with st.expander("Project info",expanded=False):
                update_project = st.button("Update Project", icon="🔄")
                if update_project:
                    st.session_state.update_project_view = True
                render_selected_project()

    llm_model_options()


if not st.session_state.project_id:
    st.title("Project View Page")
    with st.container():
        render_new_input()

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
            project_data = session_service.load_project()
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
                render_new_input(mode = "update")
            with cols[1]:
                render_selected_project()
        else:
            if st.session_state.first_question:
                render_first_question()
            else:
                display_history()
                handle_new_question()
    else:
        st.warning("No factsheet available for this project.")


#st.json(st.session_state.factsheet)