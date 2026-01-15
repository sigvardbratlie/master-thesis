import streamlit as st
import math
from typing import Optional
from uuid import uuid4
from ui.services.session_service import SessionService
from ui.utils import init_state
from ui.ui_components.attachments import view_attachment
import logging
from ui.models import AskAgentRequest, ToolResultEvent
from ui.ui_components.tool_results import handle_tool_result
from ui.ui_components.attachments import mk_attachment_payload, view_uploaded_file
from ui.services.streaming_service import StreamingService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def render_first_question() -> Optional[str]:
    """
    Renders welcome screen with example questions.

    Returns:
        Selected question text, or None if no question selected
    """
    st.session_state.session_title = None
    st.markdown(
        f"""
        <div style='text-align: center; margin-top: 200px;'>
            <h1>Velkommen {st.user.given_name}! Hva lurer du på i dag?</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Start container
    start_container = st.container(vertical_alignment="bottom", height=300, border=False)

    with start_container:
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

    if question:
        st.session_state.question_to_process = question
        st.session_state.first_question = False
        st.rerun()

    return None


def render_chat_input():
    """
    Renders chat input box.

    Returns:
        Question object from st.chat_input, or None
    """
    chat_question = st.chat_input(
        "Skriv ditt spørsmål her...",
        accept_file="multiple",
        file_type=["txt", "csv", "xlsx", "pdf"],
    )

    return chat_question


def render_sidebar(session_service: SessionService):
    """
    Renders sidebar with session history, new chat button, and agent type selector.

    Args:
        session_service: SessionService instance for loading sessions
    """
    with st.sidebar:
        # Session history
        sessions = session_service.load_user_sessions()
        st.session_state.sessions_loaded = True

        chat_history = st.container(height=300, border=False)
        with chat_history:
            if sessions:
                for session in sessions:
                    if st.button(
                        label=f"{session.title[:30]}...",
                        key=session.session_id
                    ):
                        response = session_service.load_session_history(session.session_id)
                        if response:
                            st.session_state.messages = response.events
                            st.session_state.session_id = session.session_id
                            st.session_state.session_title = response.title
                            st.session_state.first_question = False
                            st.rerun()
            else:
                st.info("Du har ingen tidligere samtaler.")

        st.divider()

        # New chat button
        if st.button("➕ Start ny samtale"):
            st.session_state.clear()
            init_state()
            st.rerun()

        st.divider()

        # Agent type selector
        agent_type = st.radio(
            "Velg samtale type:",
            ("fast", "expert"),
            horizontal=True,
            index=0
        )
        if agent_type:
            st.session_state.agent_type = agent_type

        st.info(f'Agent: **{st.session_state.agent_type}** | Modell: **{st.session_state.llm_provider}**')

        st.divider()
        st.markdown("Vedleggsoversikt for denne samtalen")
        with st.popover("📎 Vedlegg", use_container_width=False):
            st.markdown("Liste over vedlegg lastet opp i denne samtalen:")
            for e in st.session_state.get("messages", []):
                attachments = e.get("data", {}).get("attachments", [])
                if e.get("type") == "human" and attachments:
                    for att in attachments:
                        if att:
                            view_attachment(att)

        # Logout button
        st.container(height=200,border=False)
        if st.button("Logg ut"):
            st.logout()
            st.rerun()



def display_history():
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
                st.markdown(user_msg.get("data", {}).get("content", ""))
                attachments = user_msg.get("data", {}).get("attachments", [])
                for att in attachments:
                    if att:
                        view_attachment(att)

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
                        tool_event = ToolResultEvent(**msg)
                        handle_tool_result(
                            tool_event,
                            elements_container,
                            company_data_container,
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


def handle_new_question():
    """Handle new question input and streaming response"""
    question_to_process = st.session_state.question_to_process
    chat_question = render_chat_input()

    question = chat_question if not question_to_process else question_to_process
    st.session_state.question_to_process = None

    if question:
        query_id = str(uuid4())

        # Prepare attachment payload
        attachment_payload = []
        for file in question.files if hasattr(question, "files") else []:
            attachment = mk_attachment_payload(file)
            if attachment:
                attachment_payload.append(attachment)

        # Add user message to session
        user_msg = {
            "type": "human",
            "data": {
                "content": question.text if hasattr(question, "text") else question,
                "attachments": [att.model_dump() for att in attachment_payload]
            }
        }
        st.session_state.messages.append(user_msg)

        # Display user message
        with st.chat_message("user"):
            st.markdown(question.text if hasattr(question, "text") else question)

            if hasattr(question, "files") and question.files:
                files = question.files
                for f in files:
                    view_uploaded_file(f)

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
            question = question.text if hasattr(question, "text") else question
            st.write(f"Spørsmål mottatt: {type(question)}")
            request = AskAgentRequest(
                question=question,
                session_id=st.session_state.session_id,
                attachments=attachment_payload,
                query_id=query_id,
                agent_type=st.session_state.agent_type,
                llm_provider=st.session_state.llm_provider,
            )

            # Create streaming service
            streaming_service = StreamingService(
                st.session_state.backend_url,
                st.session_state.access_token
            )

            # Define callbacks
            def on_tool_result(event: ToolResultEvent):
                handle_tool_result(
                    event,
                    elements_container,
                    company_data_container,
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
                session_service = SessionService(
                    backend_url=st.session_state.backend_url,
                    user_id=st.session_state.user_id,
                    access_token=st.session_state.access_token
                )
                response = session_service.load_session_history(st.session_state.session_id)
                if response:
                    st.session_state.session_title = response.title
                    st.session_state.messages = response.events
                    st.rerun()

