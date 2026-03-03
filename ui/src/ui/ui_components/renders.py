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
    
    SUGGESTIONS = {
        ":blue[:material/description:] Analyser saken": "Gi meg en oppsummering av saken",
        ":green[:material/group:] Vis parter": "Hvem er partene i saken?",
    }

    def render_start_container(self):
        question = None

        selected = st.pills(
            label="Forslag",
            label_visibility="collapsed",
            options=self.SUGGESTIONS.keys(),
            key="selected_suggestion",
        )

        if selected:
            question = self.SUGGESTIONS[selected]

        attachments = st.session_state.get("attachments") or []
        emails = st.session_state.get("emails") or []

        if st.session_state.pop("_focus_reset_pending", False):
            for key in list(st.session_state.keys()):
                if key.startswith("focus_att_") or key.startswith("focus_email_"):
                    del st.session_state[key]

        if attachments or emails:
            with st.popover("Fokuser på dokument"):
                if attachments:
                    st.caption("Vedlegg")
                    for att in attachments:
                        if att:
                            file_id = att.get("file_id", "")
                            st.checkbox(
                                att.get("filename", "ukjent fil"),
                                key=f"focus_att_{file_id}",
                            )
                if emails:
                    if attachments:
                        st.divider()
                    st.caption("E-poster")
                    for email in emails:
                        if email:
                            email_id = email.get("email_id", "")
                            label = email.get("subject") or f"E-post {email.get('date', email_id)}"
                            st.checkbox(
                                label,
                                key=f"focus_email_{email_id}",
                            )

        user_input = st.chat_input(
            "Still et spørsmål for å komme igang...",
            accept_file="multiple",
            file_type=FileExt,
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
        user_details = self.backend_service.load_user_details(st.session_state.user_id)
        display_name = (user_details.user_first_name if user_details else None) or st.session_state.get("user_name", "gjest")

        st.session_state.session_title = None

        st.html("<div style='font-size: 3.5rem; line-height: 1; text-align: center; margin-top: 6rem;'>⚖️</div>")

        title_row = st.container()
        with title_row:
            st.title(f"Hei, {display_name}!", anchor=False)
            st.caption("Hva lurer du på i dag?")

        ""  # Spacer

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
                with st.chat_message("user"):
                    st.markdown(user_msg.get("content", {}))
                    
                    # Find attachments for this message
                    user_event_id = user_msg.get("event_id")
                    user_query_id = user_msg.get("query_id")  # Alternative match key
                    
                    for att in st.session_state.get("attachments", []):
                        if att:
                            att_event_id = att.get("event_id")
                            att_query_id = att.get("query_id")
                            
                            # Match on event_id or query_id
                            if (user_event_id and att_event_id == user_event_id) or \
                               (user_query_id and att_query_id == user_query_id):
                                self.attachment_component.view_attachment(
                                    att, 
                                    key=f"hist_{att.get('file_id', 'unknown')}_{user_event_id or user_query_id}"
                                )

            # Prepare containers for this cycle
            with st.chat_message("assistant"):
                details_expander = st.expander("Detaljer", expanded=False)
                reasoning_expander = st.expander("Tankegang", expanded=False)
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

                # Display reasoning if stored
                for msg in cycle:
                    if msg.get("type") == "ai":
                        reasoning = msg.get("data", {}).get("reasoning_stream", "")
                        if reasoning:
                            with reasoning_expander:
                                st.markdown(reasoning)

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
        Renders chat input box with an optional document focus popover.

        Returns:
            Question object from st.chat_input, or None
        """
        attachments = st.session_state.get("attachments") or []
        emails = st.session_state.get("emails") or []

        if st.session_state.pop("_focus_reset_pending", False):
            for key in list(st.session_state.keys()):
                if key.startswith("focus_att_") or key.startswith("focus_email_"):
                    del st.session_state[key]

        if attachments or emails:
            with st.popover("Fokuser på dokument"):
                if attachments:
                    st.caption("Vedlegg")
                    for att in attachments:
                        if att:
                            file_id = att.get("file_id", "")
                            st.checkbox(
                                att.get("filename", "ukjent fil"),
                                key=f"focus_att_{file_id}",
                            )
                if emails:
                    if attachments:
                        st.divider()
                    st.caption("E-poster")
                    for email in emails:
                        if email:
                            email_id = email.get("email_id", "")
                            label = email.get("subject") or f"E-post {email.get('date', email_id)}"
                            st.checkbox(
                                label,
                                key=f"focus_email_{email_id}",
                            )

        chat_question = st.chat_input(
            "Skriv ditt spørsmål her...",
            accept_file="multiple",
            file_type=FileExt,
        )
        return chat_question

    def _stream_project_update(self, streaming_service):
        """Stream the update-project-from-session endpoint and show progress."""
        payload = AskAgentRequest(
            question="Oppdater prosjektet basert på denne samtalen",
            session_id=st.session_state.session_id,
            project_id=st.session_state.project_id,
            llm_model=st.session_state.llm_model,
            query_id=str(uuid4()),
        )
        _render_project_stream_progress(
            stream_iter=streaming_service.update_project_from_session_stream(payload),
            initial_label="🔄 Oppdaterer prosjektet fra samtalen...",
            complete_label="✅ Prosjektet er oppdatert!",
        )

    def render_session_actions(self, streaming_service):
        """
        Render session-level action buttons above the chat input.

        Shows an agent-triggered confirmation when pending_project_update is set,
        otherwise shows a manual 'add session as project material' button.
        """
        pending = st.session_state.get("pending_project_update", False)
        messages = st.session_state.get("messages", [])

        if pending:
            st.info("Agenten foreslår å oppdatere prosjektet basert på samtalehistorikken.")
            col1, col2 = st.columns([3, 1])
            if col1.button("Vil du oppdatere prosjektet med hele denne samtalen?", type="primary", key="agent_update_confirm"):
                st.session_state["pending_project_update"] = False
                self._stream_project_update(streaming_service)
            if col2.button("Avslå", key="agent_update_decline"):
                st.session_state["pending_project_update"] = False
                st.rerun()

        elif messages:
            if st.button("Legg til samtale som prosjektmateriale", type="primary", key="manual_session_update"):
                self._stream_project_update(streaming_service)

    def handle_new_question(self,):
        """Handle new question input and streaming response"""
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)

        # Session actions: agent-triggered confirmation or manual button (persists across reruns)
        self.render_session_actions(streaming_service)

        question_to_process = st.session_state.question_to_process
        chat_question = self.render_chat_input()

        question = chat_question if not question_to_process else question_to_process
        st.session_state.question_to_process = None

        if question:
            query_id = str(uuid4())

            # Collect focused documents from checkbox state and build prefix
            focused_parts = []
            for att in st.session_state.get("attachments") or []:
                if att:
                    file_id = att.get("file_id", "")
                    if st.session_state.get(f"focus_att_{file_id}"):
                        focused_parts.append(f"vedlegg:{att.get('filename', file_id)}, path: {att.get('path', 'ukjent')}")
            for email in st.session_state.get("emails") or []:
                if email:
                    email_id = email.get("email_id", "")
                    if st.session_state.get(f"focus_email_{email_id}"):
                        subject = email.get("subject") or email_id
                        focused_parts.append(f"e-post:{subject}, path: {email.get('path', 'ukjent')}")
            if focused_parts:
                st.session_state["_focus_reset_pending"] = True

            raw_text = question.text if hasattr(question, "text") else question
            focus_context = f"[Fokus på: {', '.join(focused_parts)}]" if focused_parts else None

            # Prepare attachment payload
            attachment_payload = []
            email_payload = []
            for file in question.files if hasattr(question, "files") else []:
                attachment = self.attachment_component.mk_attachment_payload(file = file, query_id = query_id)
                if attachment:
                    attachment_payload.append(attachment)

            # Check for duplicate filenames within project and chat uploads
            if st.session_state.get("project_id") and attachment_payload:
                existing_filenames = {att.get("filename"): att for att in st.session_state.get("attachments", [])}

                # Check for duplicates within uploaded files themselves
                uploaded_filenames = {}
                duplicates_found = []

                for att in attachment_payload:
                    if att.filename in existing_filenames:
                        duplicates_found.append(att.filename)
                    elif att.filename in uploaded_filenames:
                        duplicates_found.append(att.filename)
                    else:
                        uploaded_filenames[att.filename] = att

                if duplicates_found:
                    st.warning(f"⚠️ Duplicate file(s) detected: **{', '.join(set(duplicates_found))}**")
                    st.info("💡 These files already exist in the project. They will be uploaded again, potentially creating duplicate embeddings.")

            # Add user message to session
            user_msg = {
                "type": "human",
                "data": {
                    "content": raw_text,
                    "attachments": [att.model_dump(mode = "json") for att in attachment_payload]
                }
            }
            st.session_state.messages.append(user_msg)

            # Display user message
            with st.chat_message("user"):
                st.markdown(raw_text)

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
                    reasoning_expander = st.expander("Tankegang", expanded=False)
                    reasoning_placeholder = reasoning_expander.empty()
                    reasoning_text = ""
                    text_container = st.container()
                    status_container = st.container()

                status_placeholder = status_container.empty()
                status_box = status_placeholder.status("🧠 Jobber med saken...", expanded=False)

                # Prepare request
                request = AskAgentRequest(
                    question=raw_text,
                    session_id=st.session_state.session_id,
                    attachments=[att.model_dump(mode = "json") for att in attachment_payload],
                    query_id=query_id,
                    project_id = st.session_state.project_id,
                    llm_model=st.session_state.llm_model,
                    focus_context=focus_context,
                )

                # Define callbacks
                def on_tool_result(event: StreamEvent):
                    self.tool_result_component.handle_tool_result(
                        event,
                        elements_container,
                        show_sql_expander=True,
                        text_container=text_container
                    )

                def on_reasoning(text: str):
                    nonlocal reasoning_text
                    reasoning_text += text
                    reasoning_placeholder.markdown(reasoning_text)

                def status_callback(label: str, state: str):
                    status_box.update(label=label, state=state)

                # Stream response
                try:
                    with text_container:
                        st.write_stream(streaming_service.stream_response(
                            request=request,
                            on_tool_result=on_tool_result,
                            on_reasoning=on_reasoning,
                            status_callback=status_callback
                        ))
                except Exception as e:
                    st.error(f"Streaming error: {e}")
                    logger.error(f"Streaming error: {e}")
                finally:
                    st.session_state.is_searching = False

                # Trigger rerun to show project update confirmation if agent requested it
                if st.session_state.get("pending_project_update"):
                    st.rerun()

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


    def llm_model_options(self, default_choice = None,expanded = False):
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
        with st.expander("Velg spesifikk modell (valgfritt)", expanded=expanded):
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
                                      options = all_models,
                                      index = default_choice)
            if custom_llm:
                st.session_state.llm_model = custom_llm.replace(" - ","_")
            else:
                st.session_state.llm_model = llm_provider+ "_" + llm_options[llm_provider][agent_type]
        st.info(f'Model: **{st.session_state.llm_model.replace("_"," - ")}**')

    def _delete_sidebar_session(self, session_id: str):
        if self.backend_service.delete_session(session_id):
            if st.session_state.get('session_id') == session_id:
                st.session_state.session_id = None
                st.session_state.messages = []
                st.session_state.session_title = None
            st.toast("Session deleted")
        else:
            st.toast("Could not delete session", icon="⚠️")

    def load_session(self, session):
        is_selected = st.session_state.get('session_id') == session.session_id
        if st.button(
            label=f"{session.title[:30]}...",
            key=session.session_id,
            use_container_width=True,
            type="primary" if is_selected else "secondary",
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
        user_first_name = st.session_state.get('user_first_name')
        user_last_name = st.session_state.get('user_last_name')
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
        st.session_state.user_first_name = user_first_name
        st.session_state.user_last_name = user_last_name
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

        if st.session_state.get('session_id'):
            st.button("Delete current session", icon=":material/delete:", type="tertiary",
                      key="del_current_session",
                      on_click=lambda: self._delete_sidebar_session(st.session_state.session_id))

        st.divider()

        # New chat button
        st.button("Start ny samtale", icon=":material/add:", on_click=self.on_session_select, type="tertiary")

        st.divider()
        self.llm_model_options()

        st.divider()
        st.markdown("Vedleggsoversikt for denne samtalen")
        attachments = st.session_state.get("attachments", [])
        if attachments:
            with st.expander(f"📎 Vedlegg ({len(attachments)})", expanded=False):
                for i, att in enumerate(attachments):
                    if att:
                        self.attachment_component.view_attachment(
                            att, 
                            key=f"sidebar_att_{att.get('file_id', i)}"
                        )
        else:
            st.caption("Ingen vedlegg i denne samtalen")

        # Logout button
        st.container(height=200, border=False)
        if st.button("Logg ut", icon=":material/logout:", type="tertiary"):
            self.auth_service.logout()
            st.rerun()


def _render_project_stream_progress(
    stream_iter,
    initial_label: str = "🔄 Processing...",
    complete_label: str = "✅ Done!",
) -> bool:
    """
    Shared progress renderer for init-project, update-project, and
    update-project-from-session streams. Accepts a pre-created iterator so
    callers control which endpoint is used.

    Returns True on success, False on error.
    """
    PHASE_CONFIG = {
        "initialization": ("🚀", "Setting up"),
        "init_input": ("📋", "Analyzing case details"),
        "storage": ("💾", "Saving documents"),
        "parse-documents": ("📑", "Parsing documents"),
        "parse_doc": ("📄", "Document parsed"),
        "analyze_docs": ("📄", "Document analysis"),
        "analyze_doc": ("📝", "Document analyzed"),
        "analyze_email": ("✉️", "Email analyzed"),
        "final_analysis": ("🔬", "Running final analysis"),
        "factual_facts": ("⚖️", "Factual analysis"),
        "governing_law": ("📜", "Legal framework analysis"),
    }

    with st.status(initial_label, expanded=True) as status:
        progress_bar = st.progress(0, text="Starting...")
        total = 0
        completed = 0

        try:
            for event in stream_iter:
                if event.get("error"):
                    status.update(label="❌ Error occurred", state="error")
                    st.error(event["error"])
                    return False

                phase_raw = event.get("phase", "")
                phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                event_status = event.get("status", "")
                data = event.get("data") or {}
                emoji, label = PHASE_CONFIG.get(phase, ("⏳", phase or "Processing"))

                if event_status == "starting":
                    n = data.get("total_operations", data.get("total", 0))
                    total += n

                    if phase == "parse_doc":
                        fname = data.get("filename", "")
                        status.update(label=f"{emoji} Parsing {fname}..." if fname else f"{emoji} {label}...")
                    elif phase == "storage":
                        fname = data.get("filename", "")
                        status.update(label=f"💾 Saving {fname} to vector store..." if fname else f"💾 {label}...")
                    else:
                        status.update(label=f"{emoji} {label}...")

                    if phase == "initialization":
                        n_att = data.get("attachments", 0)
                        if n_att:
                            st.caption(f"📎 {n_att} attachment(s) to process")
                    elif phase in ("analyze_docs", "analyze_doc"):
                        n_docs = data.get("total", 0)
                        if n_docs:
                            st.caption(f"📄 Analyzing {n_docs} document(s)...")

                elif event_status == "complete":
                    if phase == "analyze_docs":
                        continue

                    completed += 1
                    detail = ""

                    if phase == "init_input":
                        n = data.get("parties_found", 0)
                        detail = f" — {n} parties found" if n else ""
                    elif phase == "parse_doc":
                        fname = data.get("filename", "")
                        progress = data.get("progress", 0)
                        total_files = data.get("total", 0)
                        detail = f": **{fname}** ({progress}/{total_files})" if fname else ""
                    elif phase == "storage":
                        fname = data.get("filename", "")
                        storage_types = data.get("storage_type", [])
                        if fname:
                            detail = f": **{fname}**"
                        elif "file_storage" in storage_types:
                            detail = " — file storage"
                        elif "database" in storage_types:
                            detail = " — database"
                    elif phase == "analyze_doc":
                        fname = data.get("filename", "")
                        progress = data.get("progress", 0)
                        total_docs = data.get("total", 0)
                        detail = f": **{fname}** ({progress}/{total_docs})" if fname else f" ({progress}/{total_docs})"
                    elif phase == "analyze_email":
                        subject = data.get("subject", "")
                        progress = data.get("progress", 0)
                        total_docs = data.get("total", 0)
                        detail = f": **{subject}** ({progress}/{total_docs})" if subject else f" ({progress}/{total_docs})"
                    elif phase == "factual_facts":
                        d = data.get("disputed_count", 0)
                        u = data.get("undisputed_count", 0)
                        detail = f" — {d} disputed, {u} undisputed facts"
                    elif phase == "governing_law":
                        j = data.get("jurisdiction", "")
                        detail = f" — {j}" if j else ""

                    st.markdown(f"✅ {label}{detail}")

                    if phase == "storage":
                        fname = data.get("filename", "")
                        status.update(label=f"💾 Saving {fname}..." if fname else "💾 Saving documents...")
                    elif phase == "analyze_doc":
                        fname = data.get("filename", "")
                        status.update(label=f"{emoji} Analyzing {fname}..." if fname else f"{emoji} Analyzing documents...")
                    elif phase == "analyze_email":
                        subject = data.get("subject", "")
                        status.update(label=f"{emoji} Analyzing {subject}..." if subject else f"{emoji} Analyzing emails...")

                    if total > 0:
                        pct = min(completed / total, 1.0)
                        progress_bar.progress(pct, text=f"{emoji} {label}...")

            progress_bar.progress(1.0, text="Complete!")
            status.update(label=complete_label, state="complete")
            return True

        except Exception as e:
            status.update(label="❌ Error during processing", state="error")
            st.error(str(e))
            logger.error(f"Error in project stream progress: {e}", exc_info=True)
            return False


class ProjectComponent:
    def __init__(self):
        # self.streaming_service = get_streaming_service(
        #             st.session_state.backend_url,
        #             st.session_state.access_token
        #         )
        self.backend_service = get_supabase_manager()
        self.attachment_component = get_attachment_component()

    def _handle_duplicate_files(self, new_attachments: list) -> list:
        """
        Handle duplicate filenames in project uploads.
        Returns filtered list of attachments based on user choices.
        """
        if not st.session_state.get("project_id") or not new_attachments:
            return new_attachments
        
        streaming_service = get_streaming_service(
            backend_url=st.session_state.backend_url,
            access_token=st.session_state.access_token
        )
        
        # Get existing filenames
        existing_files = {att.get("filename"): att for att in st.session_state.get("attachments", [])}
        
        # Find duplicates
        duplicates = []
        seen_uploads = {}
        
        for att in new_attachments:
            if att.filename in existing_files:
                duplicates.append({
                    "filename": att.filename,
                    "type": "existing",
                    "existing": existing_files[att.filename],
                    "new": att
                })
            elif att.filename in seen_uploads:
                duplicates.append({
                    "filename": att.filename,
                    "type": "multiple_upload",
                    "first": seen_uploads[att.filename],
                    "new": att
                })
            else:
                seen_uploads[att.filename] = att
        
        if not duplicates:
            return new_attachments
        
        # Show duplicate handler UI
        st.warning(f"⚠️ Found {len(duplicates)} duplicate filename(s)")
        
        with st.expander("⚠️ Handle duplicate files", expanded=True):
            st.markdown("**Choose how to handle each duplicate:**")
            
            # Initialize choices
            if "duplicate_choices" not in st.session_state:
                st.session_state.duplicate_choices = {}
            
            for i, dup in enumerate(duplicates):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    if dup["type"] == "existing":
                        st.markdown(f"**📄 {dup['filename']}**  \n🔄 Already exists in project")
                    else:
                        st.markdown(f"**📄 {dup['filename']}**  \n🔄 Uploaded multiple times")
                
                with col2:
                    choice = st.selectbox(
                        "Action:",
                        options=["Keep both", "Replace existing", "Skip new"],
                        key=f"dup_choice_{i}_{dup['filename']}",
                        label_visibility="collapsed"
                    )
                    st.session_state.duplicate_choices[dup['filename']] = choice
        
        # Process attachments based on choices
        filtered = []
        duplicate_names = {d["filename"] for d in duplicates}
        
        for att in new_attachments:
            if att.filename not in duplicate_names:
                # No duplicate - keep it
                filtered.append(att)
                continue
            
            choice = st.session_state.duplicate_choices.get(att.filename, "Keep both")
            
            if choice == "Keep both":
                # Rename new file
                name, ext = (att.filename.rsplit('.', 1) if '.' in att.filename 
                           else (att.filename, ''))
                att.filename = f"{name}_copy.{ext}" if ext else f"{name}_copy"
                filtered.append(att)
                
            elif choice == "Replace existing":
                # Delete old file from storage, database, and vector store
                existing = existing_files.get(att.filename)
                if existing:
                    file_id = existing.get("file_id")
                    path = existing.get("path")
                    
                    # Delete from Supabase (storage + database)
                    if path:
                        self.backend_service.delete_project_file(path)
                    
                    # Delete from vector store
                    if file_id:
                        streaming_service.delete_file_vectorstore(file_id)
                    
                    logger.info(f"Replaced file {att.filename} (deleted old: {file_id})")
                
                filtered.append(att)
            
            # "Skip new" - don't add to filtered list
        
        return filtered

    def clean_element(self,):
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)
        with st.popover("Clean and update project element"):
            relational_options = ["Events", "Parties", "Claims", "Damages", "Deadlines"]
            metadata_options = ["Title", "Background", "All Metadata"]
            custom_law_options = ["Governing Law", "Disputed Facts", "Undisputed Facts"]

            selected_relational = st.multiselect("Relational elements", options=relational_options)
            selected_metadata = st.selectbox("Metadata", options=["—"] + metadata_options)
            selected_law = st.selectbox("Legal attributes", options=["—"] + custom_law_options)

            if st.button("Clean selected", icon="🧹"):
                payload = AskAgentRequest(
                    project_id=st.session_state.project_id,
                    session_id=st.session_state.session_id,
                    attachments=[],
                    question="",
                    query_id=str(uuid4()),
                    llm_model=st.session_state.llm_model,
                )

                rerun_needed = False

                # --- Relational elements (any subset) ---
                if selected_relational:
                    element_types = [e.lower() for e in selected_relational]
                    elements_payload = CleanupElementsRequest(
                        **payload.model_dump(),
                        element_types=element_types,
                    )
                    success = self._stream_cleanup_progress(
                        streaming_service.cleanup_elements_stream, elements_payload
                    )
                    if success:
                        for field in element_types:
                            st.session_state.factsheet[field] = self.backend_service.load_project_element(
                                project_id=st.session_state.project_id, element_type=field
                            )
                        rerun_needed = True

                # --- Metadata ---
                if selected_metadata != "—":
                    if selected_metadata == "All Metadata":
                        success = self._stream_cleanup_progress(
                            streaming_service.cleanup_all_metadata_stream, payload
                        )
                        if success:
                            for field in ["title", "background"]:
                                st.session_state.factsheet[field] = self.backend_service.load_project_element(
                                    project_id=st.session_state.project_id, element_type=field
                                )
                            rerun_needed = True
                    else:
                        element_key = selected_metadata.lower()
                        success = self._stream_cleanup_progress(
                            streaming_service.cleanup_attr_stream, payload, element_key
                        )
                        if success:
                            st.session_state.factsheet[element_key] = self.backend_service.load_project_element(
                                project_id=st.session_state.project_id, element_type=element_key
                            )
                            rerun_needed = True

                # --- Legal attributes ---
                if selected_law != "—":
                    element_key_map = {
                        "Disputed Facts": "disputed_facts",
                        "Undisputed Facts": "undisputed_facts",
                    }
                    element_key = element_key_map.get(selected_law, selected_law.lower().replace(" ", "_"))
                    success = self._stream_cleanup_progress(
                        streaming_service.cleanup_attr_stream, payload, element_key
                    )
                    if success:
                        st.session_state.factsheet[element_key] = self.backend_service.load_project_element(
                            project_id=st.session_state.project_id, element_type=element_key
                        )
                        rerun_needed = True

                if rerun_needed:
                    st.rerun()

    def _stream_cleanup_progress(self, streaming_function: callable, payload, element_type: str = None):
        """Display live streaming progress for cleanup operation."""
        label = element_type or "elements"
        with st.status(f"🧹 Cleaning {label}...", expanded=True) as status:
            try:
                stream = streaming_function(payload) if element_type is None else streaming_function(payload, element_type)
                for event in stream:
                    if event.get("error"):
                        status.update(label="❌ Error occurred", state="error")
                        st.error(event["error"])
                        return False

                    phase_raw = event.get("phase", "")
                    phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                    event_status = event.get("status", "")
                    data = event.get("data", {})

                    if phase.startswith("cleanup_"):
                        element = phase[len("cleanup_"):]
                        emoji, phase_label = "🧹", f"Cleaning {element}"
                    elif phase == "storage":
                        emoji, phase_label = "💾", "Saving to database"
                    else:
                        emoji, phase_label = "⏳", phase

                    if event_status == "starting":
                        status.update(label=f"{emoji} {phase_label}...")
                        original = data.get("original_count", 0)
                        if original:
                            st.caption(f"📋 {original} {data.get('element_type', label)} to process")

                    elif event_status == "complete":
                        detail = ""
                        if phase.startswith("cleanup_"):
                            original = data.get("original_count", 0)
                            cleaned = data.get("cleaned_count", 0)
                            removed = data.get("removed", 0)
                            if original or cleaned:
                                detail = f": {cleaned} kept, {removed} removed (from {original})"
                        st.markdown(f"✅ {phase_label}{detail}")

                status.update(label=f"✅ Done!", state="complete")
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
        user_first_name = st.session_state.get('user_first_name')
        user_last_name = st.session_state.get('user_last_name')
        access_token = st.session_state.get('access_token')
        refresh_token = st.session_state.get('refresh_token')
        auth_initialized = st.session_state.get('_auth_initialized')
        backend_url = st.session_state.get('backend_url')

        st.session_state.clear()
        init_state()

        # Restore auth credentials
        st.session_state.user_id = user_id
        st.session_state.user_name = user_name
        st.session_state.user_first_name = user_first_name
        st.session_state.user_last_name = user_last_name
        st.session_state.access_token = access_token
        st.session_state.refresh_token = refresh_token
        st.session_state._auth_initialized = auth_initialized
        st.session_state.backend_url = backend_url

        st.session_state.project_id = project['project_id']
        logger.info(f"Selected project: {st.session_state.project_id}")

        # Load the factsheet for the selected project
        project_data =  self.backend_service.load_project(project_id=st.session_state.project_id)
        if project_data and "factsheet" in project_data and "attachments" in project_data and "emails" in project_data:
            st.session_state.factsheet = project_data.get('factsheet')
            st.session_state.attachments = project_data.get('attachments', [])
            st.session_state.emails = project_data.get('emails', [])
            logger.info(f"Loaded factsheet for project: {st.session_state.project_id}")
        else:
            st.session_state.factsheet = None
            st.session_state.attachments = []
            st.session_state.emails = []
            logger.warning(f"No Project data found for project: {st.session_state.project_id}")

        #st.rerun()

    def _delete_project(self, project_id: str):
        """Delete project from Supabase and vector store."""
        # Delete from Supabase first
        if self.backend_service.delete_project(project_id):
            # Then delete from vector store via agent API
            streaming_service = get_streaming_service(
                backend_url=st.session_state.backend_url,
                access_token=st.session_state.access_token
            )
            result = streaming_service.delete_project_vectorstore(project_id)
            
            if result.get("success"):
                logger.info(f"Successfully deleted project {project_id} from both Supabase and vector store")
            else:
                logger.warning(f"Project {project_id} deleted from Supabase but vector store cleanup failed: {result.get('error')}")
            
            # Clear session state
            if st.session_state.get('project_id') == project_id:
                st.session_state.project_id = None
                st.session_state.factsheet = None
                st.session_state.attachments = []
                st.session_state.emails = []
            
            st.toast("Project deleted")
        else:
            st.toast("Could not delete project", icon="⚠️")

    def render_projects(self, ):
        st.header("Select Project")
        projects = self.backend_service.load_projects(user_id=st.session_state.user_id)
        if projects:
            with st.expander("Projects", expanded=True):
                for project in projects:
                    is_selected = st.session_state.get('project_id') == project.get('project_id')
                    st.button(f"{project.get('title', 'No Title')}",
                            on_click=lambda p=project: self.on_project_select(p),
                            key=project.get('project_id', 'no-id'),
                            use_container_width=True,
                            type="primary" if is_selected else "secondary")
                if st.session_state.get('project_id'):
                    st.button("Delete current project", icon=":material/delete:", type="tertiary",
                              key="del_current_project",
                              on_click=lambda: self._delete_project(st.session_state.project_id))
        else:
            st.info("No projects found. Please initialize a new project.")

    def render_selected_project(self, factsheet, key_prefix: str = ""):
        st.header("Selected Project:")
        st.markdown(f"### {factsheet.get('title')}")
        
        with st.expander("Events", expanded=False, icon="🕒"):
            events = factsheet.get('events', [])
            sorted_events = sorted(events, key=lambda x: x.get('event_start_date', '') or '')
            for event in sorted_events:
                sig = event.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sig, "⚪")
                start_date = event.get('event_start_date', 'No Date')
                end_date = event.get('event_end_date', 'No Date')
                if end_date and start_date and end_date != start_date:
                    st.markdown(f"- {sig_icon} **{start_date} - {end_date}**: {event.get('description', 'No Description')}")
                elif start_date and start_date != 'No Date':
                    st.markdown(f"- {sig_icon} **{start_date}**: {event.get('description', 'No Description')}")
                else:
                    st.markdown(f"- {sig_icon} **No Date**: {event.get('description', 'No Description')}")
        
        # elements = {"parties" : "👥", "claims" : "📄", "damages" : "💰", "deadlines" : "⏰",
        # }
        # for field, icon in elements.items():
        #     self.display_field(label = field.replace("_"," ").title(), value = field, icon = icon, factsheet=factsheet)
        with st.expander("Parties", expanded=False, icon="👥"):
            parties = factsheet.get("parties", [])
            for party in parties:
                significance = party.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                st.markdown(f"- {sig_icon} {party.get('legal_name', 'No Legal Name')} ({party.get('role', 'No Role')})")
        
        with st.expander("Claims", expanded=False, icon="📄"):
            claims = factsheet.get("claims", [])
            for claim in claims:
                significance = claim.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                st.markdown(f"- {sig_icon} {claim.get('relief_sought', 'No Relief Sought')}")
        
        with st.expander("Damages", expanded=False, icon="💰"):
            damages = factsheet.get("damages", [])
            for damage in damages:
                significance = damage.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                st.markdown(f"- {sig_icon} {damage.get('basis', 'No Basis')} | {damage.get('amount', 'No Amount')} {damage.get('currency', '')}")
        
        with st.expander("Deadlines", expanded=False, icon="⏰"):
            deadlines = factsheet.get("deadlines", [])
            for deadline in deadlines:
                significance = deadline.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                date = deadline.get('deadline_date', 'No Date',)
                st.markdown(f"- {sig_icon} **{date}**: {deadline.get('description', 'No Description')}")


        with st.expander("Background", expanded=False, icon="📚"):
            st.markdown(factsheet.get("background", ""))
        
        # with st.expander("disputed & undisputed facts", expanded=False, icon="⚔️"):
        #     disputed_facts = factsheet.get('disputed_facts', [])
        #     with st.expander("Disputed Facts", expanded=False, icon="❌"):
        #         for fact in disputed_facts:
        #             st.markdown(f"- {fact}")
            
        #     with st.expander("Undisputed Facts", expanded=True, icon="✅"):
        #         for fact in factsheet.get('undisputed_facts', []):
        #             st.markdown(f"- {fact}")
            

        with st.expander("Attachments Overview", expanded=False, icon="📎"):
            sorted_attachments = sorted(
                st.session_state.get('attachments', []),
                key=lambda x: x.get('file_date', '') or '',
                reverse=True
            )
            for file in sorted_attachments:
                sig = file.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sig, "⚪")
                self.attachment_component.view_attachment(file, key=f"{key_prefix}proj_att_{file.get('file_id', '')}", sig_icon=sig_icon)

        with st.expander("Correspondence Overview", expanded=False, icon="✉️"):
            sorted_emails = sorted(
                st.session_state.get("emails", []),
                key=lambda x: x.get('date', '') or '',
                reverse=True
            )
            for file in sorted_emails:
                sig = file.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sig, "⚪")
                email_att = {
                    "file_id": file.get("email_id"),
                    "filename": file.get("subject", "No Subject"),
                    "file_type": "message/rfc822",
                    "body": file.get("body"),
                    "from_addr": file.get("from_addr", file.get("from", "")),
                    "to": file.get("to", []),
                    "subject": file.get("subject", ""),
                    "date": str(file.get("date", "")),
                }
                self.attachment_component.view_attachment(email_att, key=f"{key_prefix}proj_email_{file.get('email_id', '')}", sig_icon=sig_icon)

    def _delete_session(self, session_id: str):
        if self.backend_service.delete_session(session_id):
            if st.session_state.get('session_id') == session_id:
                st.session_state.session_id = None
                st.session_state.messages = []
                st.session_state.session_title = None
            st.toast("Session deleted")
        else:
            st.toast("Could not delete session", icon="⚠️")

    def render_project_sessions(self):
        sessions = self.backend_service.load_project_sessions(project_id=st.session_state.project_id)
        if sessions:
            for session in sessions:
                is_selected = st.session_state.get('session_id') == session.session_id
                session_selected = st.button(
                    f"{session.title if session.title else 'No Title'}",
                    key=f"psession_{session.session_id}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                )
                if session_selected:
                    history = self.backend_service.load_session_history(session.session_id)
                    st.session_state.messages = history.events
                    st.session_state.session_id = session.session_id
                    st.session_state.session_title = session.title
                    st.session_state.first_question = None
                    logger.info(f"Selected session: {st.session_state.session_id}")
                    st.rerun()
            if st.session_state.get('session_id'):
                st.button("Delete current session", icon=":material/delete:", type="tertiary",
                          key="del_current_psession",
                          on_click=lambda: self._delete_session(st.session_state.session_id))
        else:
            st.info("No sessions found for this project.")

        
    def _stream_init_progress(self, streaming_service, payload):
        """Display live streaming progress for project initialization."""
        return _render_project_stream_progress(
            stream_iter=streaming_service.init_project_stream(payload),
            initial_label="🚀 Initializing project...",
            complete_label="✅ Project initialized!",
        )

    def _stream_update_progress(self, streaming_service, payload):
        """Display live streaming progress for project update."""
        return _render_project_stream_progress(
            stream_iter=streaming_service.update_project_stream(payload),
            initial_label="🔄 Updating project...",
            complete_label="✅ Project updated!",
        )

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
                                    type=FileExt,
                                    help="You can upload multiple files.",
                                    key = f"file_uploader_{st.session_state.clear_input_counter}")
        
        # Process uploaded files
        attachment_list = [self.attachment_component.mk_attachment_payload(f, query_id=query_id) 
                          for f in user_files] if user_files else []
        all_attachments = [att for att in attachment_list if att]
        
        # Handle duplicate filenames (with UI for user choice)
        all_attachments = self._handle_duplicate_files(all_attachments)

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
        user_first_name = st.session_state.get('user_first_name')
        user_last_name = st.session_state.get('user_last_name')
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
        st.session_state.user_first_name = user_first_name
        st.session_state.user_last_name = user_last_name
        st.session_state.access_token = access_token
        st.session_state.refresh_token = refresh_token
        st.session_state._auth_initialized = auth_initialized
        st.session_state.backend_url = backend_url
        st.session_state.project_id = project_id
        logger.info(f"Initialized new session: {st.session_state.session_id}")
        #st.rerun()

    def run_sidebar(self,):
        new_project = st.button("Initialize New Project", icon=":material/add_circle:", type="tertiary")
        if new_project:
            st.session_state.clear()
            init_state()
            st.rerun()

        st.divider()
        self.render_projects()
        st.divider()
        if st.session_state.get('project_id', None):
            project_title = st.session_state.get('factsheet', {}).get('title', '') if st.session_state.get('factsheet') else ''
            if project_title:
                st.caption(f"Aktivt prosjekt: **{project_title}**")
            with st.expander("Project Sessions", expanded=True):
                self.render_project_sessions()
                st.button("New session", icon=":material/chat:", on_click=self.on_session_select, type="tertiary")

            st.divider()
            if st.session_state.get('factsheet', None):
                with st.expander("Project info", expanded=False):
                    cols = st.columns(2)
                    update_project = cols[0].button("Update Project", icon=":material/refresh:", type="tertiary")
                    if update_project:
                        st.session_state.update_project_view = True
                    with cols[1]:
                        self.clean_element()

                    self.render_selected_project(factsheet=st.session_state.factsheet, key_prefix="sidebar_")



def get_project_component() -> ProjectComponent:
    """Cached ProjectComponent instance"""
    return ProjectComponent()

def get_chat_component() -> ChatComponent:
    """Cached ChatComponent instance"""
    return ChatComponent()

def get_sidebar_component() -> SidebarComponent:
    """Cached SidebarComponent instance"""
    return SidebarComponent()