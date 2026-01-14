import streamlit as st
import math
from typing import Optional
from uuid import uuid4
from ui.services.session_service import SessionService
from ui.utils import init_state
from ui.ui_components.attachments import view_attachment

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


