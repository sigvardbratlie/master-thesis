import streamlit as st
import math
from typing import Optional
from uuid import uuid4
#from ui.services.session_service import SessionService
from ui.utils import init_state
import logging
from ui.models import *
from ui.ui_components.tool_results import ToolResultComponent, get_tool_result_component
from ui.ui_components.attachments import AttachmentComponent, get_attachment_component
from ui.services import get_streaming_service, get_supabase_manager,get_supabase_auth_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatComponent:
    def __init__(self):
        # self.streaming_service = get_streaming_service(
        #     st.session_state.backend_url,
        #     st.session_state.access_token
        # )
        self.backend_service = get_supabase_manager()
        self.attachment_component = get_attachment_component()
        self.tool_result_component = get_tool_result_component()
    
    def render_start_container(self):
        max_per_row = 4
        questions = [
            "Spørsmål 1",
            "Spørsmål 2",
        ]

        rows = math.ceil(len(questions) / max_per_row)
        question = None
        q_idx = 0

        for i in range(rows):
            row_questions = questions[q_idx: q_idx + max_per_row]
            row_length = len(row_questions)
            cols = st.columns(
                row_length,
                vertical_alignment="center",
                gap="small",
                width="stretch",
            )
            for idx, q in enumerate(row_questions):
                button_key = f"question_btn_{q_idx + idx}"
                if cols[idx].button(q, key=button_key):
                    question = q
            q_idx += max_per_row

        user_input = st.chat_input(
            "Still et spørsmål for å komme igang...",
            accept_file="multiple",
            file_type=["txt", "csv", "xlsx", "pdf"],
        )
        if user_input:
            question = user_input

        return question

    def render_first_question(self) -> Optional[str]:
        """
        Renders welcome screen with example questions.

        Returns:
            Selected question text, or None if no question selected
        """
        st.session_state.session_title = None
        st.markdown(
            f"""
            <div style='text-align: center; margin-top: 200px;'>
                <h1>Velkommen {st.session_state.user_name if "user_name" in st.session_state else "gjest"}! Hva lurer du på i dag?</h1>
            </div>
            """,
            unsafe_allow_html=True
        )

        # Start container
        start_container = st.container(vertical_alignment="bottom", height=300, border=False)

        with start_container:
            question = self.render_start_container()

        if question:
            st.session_state.question_to_process = question
            st.session_state.first_question = False
            st.rerun()

        return None

    def display_history(self, ):
        """Display chat history with all messages"""
        # Group messages by query cycle (each human message starts a new cycle)
        cycles = []
        current_cycle = []
        for msg in st.session_state.messages:
            if msg.get("type") == "human":
                if current_cycle:
                    cycles.append(current_cycle)
                current_cycle = [msg]
            else:
                current_cycle.append(msg)
        if current_cycle:
            cycles.append(current_cycle)

        # Display each cycle
        for cycle in cycles:
            # Display user message
            user_msg = next((m for m in cycle if m.get("type") == "human"), None)
            if user_msg:
                #st.info(user_msg)
                with st.chat_message("user"):
                    st.markdown(user_msg.get("content", {}))
                    for att in st.session_state.attachments:
                        if att.get("event_id") == user_msg.get("event_id"):
                            self.attachment_component.view_attachment(att)

            # Prepare containers for this cycle
            with st.chat_message("assistant"):
                details_expander = st.expander("Detaljer", expanded=False)
                elements_container = st.container()
                company_data_container = st.container()
                text_container = st.container()

                # Collect details for expander
                tool_calls_msgs = []
                sql_queries = []

                for msg in cycle:
                    if msg.get("type") == "ai" and msg.get("data", {}).get("tool_calls"):
                        tool_calls_msgs.append(msg)
                    elif msg.get("type") == "tool_result" and msg.get("tool_args"):
                        sql_queries.append(msg)

                # Display details in expander
                if tool_calls_msgs or sql_queries:
                    with details_expander:
                        for ai_msg in tool_calls_msgs:
                            for tool_call in ai_msg.get("data").get("tool_calls", []):
                                if tool_call.get("name"):
                                    st.markdown(f"**Verktøy kalt:** {tool_call.get('name')}")
                                    st.markdown("**Argumenter:**")
                                    st.json(tool_call.get("args", {}))
                                    st.divider()

                        for sql_msg in sql_queries:
                            if sql_msg.get("tool_name") == "run_query":
                                st.markdown("**SQL-spørring:**")
                                st.code(sql_msg.get("tool_args", {}).get("sql_query", ""), language="sql")
                                st.divider()

                # Display tool results
                for msg in cycle:
                    if msg.get("type") == "tool_result":
                        try:
                            #tool_event = ToolResultEvent(**msg.get("data"))
                            tool_event = StreamEvent(data = ToolResultData(**msg['data']),
                                                    **{k: msg[k] for k in msg if k != 'data'})
                            self.tool_result_component.handle_tool_result(
                                tool_event,
                                elements_container,
                                show_sql_expander=False,
                                text_container=text_container
                            )
                        except Exception as e:
                            logger.error(f"Error handling tool result in history: {e}")

                # Display final answer
                for msg in cycle:
                    if msg.get("type") == "ai":
                        data = msg.get("data", {})
                        token_stream_displayed = data.get("token_stream", "")
                        if token_stream_displayed:
                            with text_container:
                                st.markdown(token_stream_displayed)
                                st.divider()

    def render_chat_input(self,):
        """
        Renders chat input box.

        Returns:
            Question object from st.chat_input, or None
        """
        chat_question = st.chat_input(
            "Skriv ditt spørsmål her...",
            accept_file="multiple",
            file_type=["txt", "csv",  "pdf", "xlsx", "docx", "eml"],
        )

        return chat_question

    def handle_new_question(self,):
        """Handle new question input and streaming response"""
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)
        question_to_process = st.session_state.question_to_process
        chat_question = self.render_chat_input()

        question = chat_question if not question_to_process else question_to_process
        st.session_state.question_to_process = None

        if question:
            query_id = str(uuid4())

            # Prepare attachment payload
            attachment_payload = []
            email_payload = []
            for file in question.files if hasattr(question, "files") else []:
                attachment = self.attachment_component.mk_attachment_payload(file = file, query_id = query_id)
                if attachment:
                    attachment_payload.append(attachment)

            # Add user message to session
            user_msg = {
                "type": "human",
                "data": {
                    "content": question.text if hasattr(question, "text") else question,
                    "attachments": [att.model_dump(mode = "json") for att in attachment_payload]
                }
            }
            st.session_state.messages.append(user_msg)

            # Display user message
            with st.chat_message("user"):
                st.markdown(question.text if hasattr(question, "text") else question)

                if hasattr(question, "files") and question.files:
                    files = question.files
                    for f in files:
                        self.attachment_component.view_uploaded_file(f)

            # Display assistant response
            with st.chat_message("assistant"):
                answer_container = st.container()
                with answer_container:
                    elements_container = st.container()
                    company_data_container = st.container()
                    details_expander = st.expander("Detaljer", expanded=False)
                    text_container = st.container()
                    status_container = st.container()

                status_placeholder = status_container.empty()
                status_box = status_placeholder.status("🧠 Jobber med saken...", expanded=False)

                # Prepare request
                request = AskAgentRequest(
                    question=question.text if hasattr(question, "text") else question,
                    session_id=st.session_state.session_id,
                    attachments=[att.model_dump(mode = "json") for att in attachment_payload],
                    query_id=query_id,
                    project_id = st.session_state.project_id,
                    llm_model=st.session_state.llm_model,
                )

                # Define callbacks
                def on_tool_result(event: StreamEvent):
                    self.tool_result_component.handle_tool_result(
                        event,
                        elements_container,
                        show_sql_expander=True,
                        text_container=text_container
                    )

                def status_callback(label: str, state: str):
                    status_box.update(label=label, state=state)

                # Stream response
                try:
                    with text_container:
                        st.write_stream(streaming_service.stream_response(
                            request=request,
                            on_tool_result=on_tool_result,
                            status_callback=status_callback
                        ))
                except Exception as e:
                    st.error(f"Streaming error: {e}")
                    logger.error(f"Streaming error: {e}")
                finally:
                    st.session_state.is_searching = False

                # Reload session title if needed
                if not st.session_state.session_title or st.session_state.session_title == "Ny samtale":
                    st.cache_data.clear()
                    # session_service = SessionService(
                    #     backend_url=st.session_state.backend_url,
                    #     user_id=st.session_state.user_id,
                    #     access_token=st.session_state.access_token
                    # )
                    response = self.backend_service.load_session_history(st.session_state.session_id)
                    st.info(response)
                    if response:
                        st.session_state.session_title = response.title
                        st.session_state.messages = response.events
                        st.rerun()


class SidebarComponent:
    def __init__(self,):
        self.backend_service = get_supabase_manager()
        self.attachment_component = get_attachment_component()
        self.auth_service = get_supabase_auth_service()


    def llm_model_options(self):
        llm_options = {
        "openai": {"fast" : "gpt-4o-mini", "expert": "gpt-4o"},
        "google": {"fast": "gemini-2.5-flash", "expert": "gemini-2.5-pro"},}

        # Agent type selector
        agent_type = st.radio(
            "Velg modell type:",
            ("fast", "expert"),
            horizontal=True,
            index=0
        )
        with st.expander("Velg spesifikk modell (valgfritt)"):
            llm_provider = st.radio(
                "Velg LLM leverandør:",
                ("openai", "google", 
                #"claude"
                ),
                horizontal=True,
                index=1
            )
        
            all_models = []
            for provider, types in llm_options.items():
                for _, model in types.items():
                    all_models.append(f"{provider} - {model}")
            custom_llm = st.selectbox("Velg spesifikk modell (valgfritt):",
                                      options = all_models)
            if custom_llm:
                st.session_state.llm_model = custom_llm.replace(" - ","_")
            else:
                st.session_state.llm_model = llm_provider+ "_" + llm_options[llm_provider][agent_type]
        st.info(f'Model: **{st.session_state.llm_model.replace("_"," - ")}**')

    def load_session(self, session):
        if st.button(
            label=f"{session.title[:30]}...",
            key=session.session_id
        ):
            response = self.backend_service.load_session_history(session.session_id)
            if response:
                st.session_state.messages = response.events
                st.session_state.attachments = response.attachments
                st.session_state.project_id = response.project_id
                st.session_state.session_id = session.session_id
                st.session_state.session_title = response.title
                st.session_state.first_question = False
                st.rerun()

    def on_session_select(self):
        user_id = st.session_state.get('user_id')
        user_name = st.session_state.get('user_name')
        access_token = st.session_state.get('access_token')
        refresh_token = st.session_state.get('refresh_token')
        auth_initialized = st.session_state.get('_auth_initialized')
        backend_url = st.session_state.get('backend_url')
        project_id = st.session_state.project_id

        st.session_state.clear()
        init_state()
        
        # Restore auth credentials
        st.session_state.user_id = user_id
        st.session_state.user_name = user_name
        st.session_state.access_token = access_token
        st.session_state.refresh_token = refresh_token
        st.session_state._auth_initialized = auth_initialized
        st.session_state.backend_url = backend_url
        st.session_state.project_id = project_id
        logger.info(f"Initialized new session: {st.session_state.session_id}")
        #st.rerun()

    def render_sidebar(self):
        """
        """
        # Session history
        sessions = self.backend_service.load_user_sessions(user_id=st.session_state.user_id)
        #st.json(sessions)
        st.session_state.sessions_loaded = True

        chat_history = st.container(height=300, border=False)
        with chat_history:
            if sessions:
                for session in sessions:
                    self.load_session(session)
            else:
                st.info("Du har ingen tidligere samtaler.")

        st.divider()

        # New chat button
        st.button("➕ Start ny samtale", on_click=self.on_session_select)

        st.divider()
        self.llm_model_options()

        st.divider()
        st.markdown("Vedleggsoversikt for denne samtalen")
        with st.popover("📎 Vedlegg", use_container_width=False):
            st.markdown("Liste over vedlegg lastet opp i denne samtalen:")
            for att in st.session_state.get("attachments", []):
                if att:
                    self.attachment_component.view_attachment(att)

        # Logout button
        st.container(height=200,border=False)
        if st.button("Logg ut"):
            self.auth_service.logout()
            st.rerun()


class ProjectComponent:
    def __init__(self):
        # self.streaming_service = get_streaming_service(
        #             st.session_state.backend_url,
        #             st.session_state.access_token
        #         )
        self.backend_service = get_supabase_manager()
        self.attachment_component = get_attachment_component()

    def clean_element(self,):
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)
        with st.popover("Clean and update project element"):
            relational_elements = ["Events", "Parties", "Governing Law", "Claims", "Damages", "Deadlines",]
            metadata_elements = ["Background","Title"]
            custom_law_elements =  ["Governing Law","Disputed & Undisputed Facts"]
            element_to_clean = st.selectbox("Select element to clean", options=relational_elements + metadata_elements + custom_law_elements)
            if st.button("Clean Element", icon="🧹"):
                element_key = element_to_clean.lower().replace(" ","_")
                if element_key:
                    if element_to_clean in relational_elements:
                        payload = AskAgentRequest(
                            project_id=st.session_state.project_id,
                            session_id=st.session_state.session_id,
                            attachments=[],
                            question="",
                            query_id=str(uuid4()),
                            llm_model=st.session_state.llm_model,
                        )
                        success = self._stream_cleanup_progress(streaming_service, payload, element_key)
                        if success:
                            project_element = self.backend_service.load_project_element(
                                project_id=st.session_state.project_id,
                                element_type=element_key)
                            st.session_state.factsheet[element_key] = project_element
                            st.rerun()
                    elif element_to_clean in metadata_elements:
                        pass #implement
                    elif element_to_clean in custom_law_elements:
                        pass

    def _stream_cleanup_progress(self, streaming_service, payload, element_type):
        """Display live streaming progress for cleanup element."""

        PHASE_CONFIG = {
            f"cleanup_{element_type}": ("🧹", f"Cleaning {element_type}"),
            "storage": ("💾", "Saving to database"),
        }

        with st.status(f"🧹 Cleaning {element_type}...", expanded=True) as status:
            try:
                for event in streaming_service.cleanup_project_element_stream(payload, element_type):
                    if event.get("error"):
                        status.update(label="❌ Error occurred", state="error")
                        st.error(event["error"])
                        return False

                    phase_raw = event.get("phase", "")
                    phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                    event_status = event.get("status", "")
                    data = event.get("data", {})
                    emoji, label = PHASE_CONFIG.get(phase, ("⏳", phase))

                    if event_status == "starting":
                        status.update(label=f"{emoji} {label}...")
                        original = data.get("original_count", 0)
                        if original:
                            st.caption(f"📋 {original} {element_type} to process")

                    elif event_status == "complete":
                        detail = ""
                        if phase == f"cleanup_{element_type}":
                            original = data.get("original_count", 0)
                            cleaned = data.get("cleaned_count", 0)
                            removed = data.get("removed", 0)
                            detail = f": {cleaned} kept, {removed} removed (from {original})"
                        st.markdown(f"✅ {label}{detail}")

                status.update(label=f"✅ {element_type.title()} cleaned!", state="complete")
                return True

            except Exception as e:
                status.update(label="❌ Error during cleanup", state="error")
                st.error(str(e))
                logger.error(f"Error during cleanup progress: {e}", exc_info=True)
                return False

    def clean_factsheet(self,):
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)
        if st.button("Clean Factsheet", icon="🧹"):
            response = streaming_service.cleanup_factsheet(
                AskAgentRequest(
                    project_id=st.session_state.project_id,
                    session_id=st.session_state.session_id,
                    attachments=[],
                    question="",
                    query_id=str(uuid4()),
                    llm_model=st.session_state.llm_model,
                ),
            )
            if response.status_code == 200 and response.json().get("success") == True:
                response_json = response.json()
                st.session_state.factsheet = response_json.get('data')
                st.success(f"{response_json.get('message')}")
                st.rerun()


    def display_field(self, label,value, icon,factsheet):
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

    def on_project_select(self, project : dict):
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
        project_data =  self.backend_service.load_project(project_id=st.session_state.project_id)
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

    def render_projects(self, ):
        st.header("Select Project")
        projects = self.backend_service.load_projects(user_id=st.session_state.user_id)
        if projects:
            with st.expander("Projects", expanded=True):
                for project in projects:
                    st.button(f"{project.get('title', 'No Title')}", 
                            on_click=lambda p=project: self.on_project_select(p), 
                            key = project.get('project_id','no-id'))
                    
        else:
            st.info("No projects found. Please initialize a new project.")

    def render_selected_project(self, factsheet):
        st.header("Selected Project:")
        st.markdown(f"### {factsheet.get('title')}")
        
        with st.expander("Events", expanded=False, icon="🕒"):
            events = factsheet.get('events', [])
            sorted_events = sorted(events, key=lambda x: x.get('event_date', ''))
            for event in sorted_events:
                start_date = event.get('event_start_date', 'No Date')
                end_date = event.get('event_end_date', 'No Date')
                if end_date and start_date and end_date != start_date:
                    st.markdown(f"**{start_date} - {end_date}**: {event.get('description', 'No Description')}")
                elif start_date and start_date != 'No Date':
                    st.markdown(f"**{start_date}**: {event.get('description', 'No Description')}")
                else:
                    st.markdown(f"**No Date**: {event.get('description', 'No Description')}")
        
        elements = {"parties" : "👥", "governing_law" : "⚖️", "claims" : "📄", "damages" : "💰", "deadlines" : "⏰",
        }
        for field, icon in elements.items():
            self.display_field(label = field.replace("_"," ").title(), value = field, icon = icon, factsheet=factsheet)
        
        with st.expander("Background", expanded=False, icon="📚"):
            st.markdown(factsheet.get("background", ""))
        
        with st.expander("disputed & undisputed facts", expanded=False, icon="⚔️"):
            disputed_facts = factsheet.get('disputed_facts', [])
            with st.expander("Disputed Facts", expanded=False, icon="❌"):
                for fact in disputed_facts:
                    st.markdown(f"- {fact}")
            
            with st.expander("Undisputed Facts", expanded=True, icon="✅"):
                for fact in factsheet.get('undisputed_facts', []):
                    st.markdown(f"- {fact}")
            

        with st.expander("Attachments Overview", expanded=False, icon="📎"):
            for file in st.session_state.get('attachments', []):
                self.attachment_component.view_attachment(file, key = str(uuid4()))
                #
                # if st.button(f"- **{file.get('filename', 'No Filename')}** ({file.get('category', 'No Category')}, {file.get('significance', 'No Significance')})", key=file.get('file_id','no-id')):
                #     st.pdf()


    def render_project_sessions(self):
        #st.header("Project Sessions")
        sessions = self.backend_service.load_project_sessions(project_id=st.session_state.project_id)
        if sessions:
            for session in sessions:
                session_selected = st.button(f"- **Session ID**: {session.session_id}, **Title**: {session.title if session.title else 'No Title'}")
                if session_selected:
                    history = self.backend_service.load_session_history(session.session_id)
                    #st.info(history)
                    st.session_state.messages = history.events
                    st.session_state.session_id = session.session_id
                    st.session_state.session_title = session.title
                    st.session_state.first_question = None
                    logger.info(f"Selected session: {st.session_state.session_id}")
                    st.rerun()
        else:
            st.info("No sessions found for this project.")

        
    def _stream_init_progress(self, streaming_service, payload):
        """Display live streaming progress for project initialization."""

        PHASE_CONFIG = {
            "initialization": ("🚀", "Setting up project"),
            "init_input": ("📋", "Analyzing case details"),
            "storage": ("💾", "Saving documents"),
            "analyze_docs": ("📄", "Starting document analysis"),
            "analyze_doc": ("📝", "Document analyzed"),
            "final_analysis": ("🔬", "Running final analysis"),
            "factual_facts": ("⚖️", "Factual analysis"),
            "governing_law": ("📜", "Legal framework analysis"),
        }

        with st.status("🚀 Initializing project...", expanded=True) as status:
            progress_bar = st.progress(0, text="Starting...")
            total = 0
            completed = 0

            try:
                for event in streaming_service.init_project_stream(payload):
                    if event.get("error"):
                        status.update(label="❌ Error occurred", state="error")
                        st.error(event["error"])
                        return False

                    phase_raw = event.get("phase", "")
                    phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                    event_status = event.get("status", "")
                    data = event.get("data", {})
                    emoji, label = PHASE_CONFIG.get(phase, ("⏳", phase))

                    if event_status == "starting":
                        n = data.get("total_operations", data.get("total", 0))
                        total += n
                        status.update(label=f"{emoji} {label}...")

                        if phase == "initialization":
                            n_att = data.get("attachments", 0)
                            if n_att:
                                st.caption(f"📎 {n_att} attachment(s) to process")

                    elif event_status == "complete":
                        # analyze_docs/complete is a summary event, skip counting
                        if phase == "analyze_docs":
                            continue

                        completed += 1

                        # Build detail text per phase
                        detail = ""
                        if phase == "init_input":
                            n = data.get("parties_found", 0)
                            detail = f" — {n} parties found" if n else ""
                        elif phase == "analyze_doc":
                            fname = data.get("filename", "")
                            detail = f": **{fname}**" if fname else ""
                        elif phase == "factual_facts":
                            d = data.get("disputed_count", 0)
                            u = data.get("undisputed_count", 0)
                            detail = f" — {d} disputed, {u} undisputed facts"
                        elif phase == "governing_law":
                            j = data.get("jurisdiction", "")
                            detail = f" — {j}" if j else ""

                        st.markdown(f"✅ {label}{detail}")

                        # Update progress bar
                        if total > 0:
                            pct = min(completed / total, 1.0)
                            progress_bar.progress(pct, text=f"{emoji} {label}...")

                # Stream finished
                progress_bar.progress(1.0, text="Complete!")
                status.update(label="✅ Project initialized!", state="complete")
                return True

            except Exception as e:
                status.update(label="❌ Error during initialization", state="error")
                st.error(str(e))
                logger.error(f"Error during init progress: {e}", exc_info=True)
                return False

    def _stream_update_progress(self, streaming_service, payload):
        """Display live streaming progress for project update."""

        PHASE_CONFIG = {
            "initialization": ("🚀", "Setting up update"),
            "storage": ("💾", "Saving documents"),
            "analyze_docs": ("📄", "Document analysis"),
            "analyze_doc": ("📝", "Document analyzed"),
        }

        with st.status("🔄 Updating project...", expanded=True) as status:
            progress_bar = st.progress(0, text="Starting...")
            total = 0
            completed = 0

            try:
                for event in streaming_service.update_project_stream(payload):
                    if event.get("error"):
                        status.update(label="❌ Error occurred", state="error")
                        st.error(event["error"])
                        return False

                    phase_raw = event.get("phase", "")
                    phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                    event_status = event.get("status", "")
                    data = event.get("data", {})
                    emoji, label = PHASE_CONFIG.get(phase, ("⏳", phase))

                    if event_status == "starting":
                        n = data.get("total_operations", data.get("total", 0))
                        total += n
                        status.update(label=f"{emoji} {label}...")

                        n_att = data.get("attachments", 0)
                        if n_att:
                            st.caption(f"📎 {n_att} attachment(s) to process")

                    elif event_status == "complete":
                        if phase == "analyze_docs":
                            continue

                        completed += 1

                        detail = ""
                        if phase == "analyze_doc":
                            fname = data.get("filename", "")
                            detail = f": **{fname}**" if fname else ""
                        elif phase == "storage":
                            storage_types = data.get("storage_type", [])
                            if "database" in storage_types:
                                detail = " — database"

                        st.markdown(f"✅ {label}{detail}")

                        if total > 0:
                            pct = min(completed / total, 1.0)
                            progress_bar.progress(pct, text=f"{emoji} {label}...")

                progress_bar.progress(1.0, text="Complete!")
                status.update(label="✅ Project updated!", state="complete")
                return True

            except Exception as e:
                status.update(label="❌ Error during update", state="error")
                st.error(str(e))
                logger.error(f"Error during update progress: {e}", exc_info=True)
                return False

    def render_new_project_input(self, mode : Literal["update","init"] = "init"):
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)
        user_input = st.text_area("Project details",
                                placeholder="Describe your project here...",
                                help="Provide details about your project to initialize it.",
                                height=150,
                                key = f"project_input_{st.session_state.clear_input_counter}")
        if "clear_input_counter" not in st.session_state:
            st.session_state.clear_input_counter = 0
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

        query_id = str(uuid4())
        project_id = st.session_state.project_id if st.session_state.project_id else str(uuid4())

        user_files = st.file_uploader("Upload project files:",
                                    accept_multiple_files=True,
                                    type=["txt", "csv", "xlsx", "docx", "pdf", "eml", ],
                                    help="You can upload multiple files.",
                                    key = f"file_uploader_{st.session_state.clear_input_counter}")
        attachment_list = [self.attachment_component.mk_attachment_payload(f,query_id=query_id) for f in user_files] if user_files else []
        
        # Flatten attachments and emails from all files
        all_attachments = []
        for attachment in attachment_list:
            if attachment:
                all_attachments.append(attachment)

        payload = AskAgentRequest(
            question=user_input,
            attachments=[att.model_dump(mode = "json") for att in all_attachments],
            session_id=st.session_state.session_id,
            query_id=query_id,
            llm_model=st.session_state.llm_model,
            project_id=project_id
        )

        init_project = st.button("Initialize Project", icon="🚀") if mode == "init" else st.button("Update Project", icon="🚀")
        if init_project:
            st.session_state.project_id = project_id
            if mode == "init":
                success = self._stream_init_progress(streaming_service, payload)
                if success:
                    project_data = self.backend_service.load_project(project_id=project_id)
                    if project_data:
                        st.session_state.factsheet = project_data.get('factsheet')
                        st.session_state.attachments = project_data.get('attachments', [])
                        st.session_state.update_project_view = True
                        st.session_state.clear_input_counter += 1
                        st.rerun()
                    else:
                        st.warning("Project saved but could not load data. Please refresh.")
            else:
                success = self._stream_update_progress(streaming_service, payload)
                if success:
                    project_data = self.backend_service.load_project(project_id=st.session_state.project_id)
                    if project_data:
                        st.session_state.factsheet = project_data.get('factsheet')
                        st.session_state.attachments = project_data.get('attachments', [])
                        st.session_state.update_project_view = True
                        st.session_state.clear_input_counter += 1
                        st.rerun()
                    else:
                        st.warning("Project updated but could not load data. Please refresh.")

    def on_session_select(self,):
        user_id = st.session_state.get('user_id')
        user_name = st.session_state.get('user_name')
        access_token = st.session_state.get('access_token')
        refresh_token = st.session_state.get('refresh_token')
        auth_initialized = st.session_state.get('_auth_initialized')
        backend_url = st.session_state.get('backend_url')
        project_id = st.session_state.project_id

        st.session_state.clear()
        init_state()
        
        # Restore auth credentials
        st.session_state.user_id = user_id
        st.session_state.user_name = user_name
        st.session_state.access_token = access_token
        st.session_state.refresh_token = refresh_token
        st.session_state._auth_initialized = auth_initialized
        st.session_state.backend_url = backend_url
        st.session_state.project_id = project_id
        logger.info(f"Initialized new session: {st.session_state.session_id}")
        #st.rerun()

    def run_sidebar(self,):
        new_project = st.button("Initialize New Project", icon="🆕")
        if new_project:
            st.session_state.clear()
            init_state()
            st.rerun()

        st.divider()
        self.render_projects()
        st.divider()
        if st.session_state.get('project_id', None):
            with st.expander("Project Sessions", expanded=True):
                self.render_project_sessions()
                #st.divider()
                st.button("New session", icon="💬",on_click=self.on_session_select)
                    
            st.divider()
            if st.session_state.get('factsheet', None):
                with st.expander("Project info",expanded=False):
                    cols = st.columns(2)
                    update_project = cols[0].button("Update Project", icon="🔄")
                    if update_project:
                        st.session_state.update_project_view = True
                    with cols[1]:
                        self.clean_element()
                    
                    self.render_selected_project(factsheet=st.session_state.factsheet)



def get_project_component() -> ProjectComponent:
    """Cached ProjectComponent instance"""
    return ProjectComponent()

def get_chat_component() -> ChatComponent:
    """Cached ChatComponent instance"""
    return ChatComponent()

def get_sidebar_component() -> SidebarComponent:
    """Cached SidebarComponent instance"""
    return SidebarComponent()