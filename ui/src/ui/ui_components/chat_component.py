import streamlit as st
from uuid import uuid4
from ui.utils import init_state
import logging
from ui.models import *
from ui.ui_components.tool_results import get_tool_result_component
from ui.ui_components.attachments import get_attachment_component
from ui.services import get_streaming_service, get_supabase_manager
from .utils_component import _render_project_stream_progress

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

    def render_first_question(self) -> str | None:
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


def get_chat_component() -> ChatComponent:
    """Cached ChatComponent instance"""
    return ChatComponent()

