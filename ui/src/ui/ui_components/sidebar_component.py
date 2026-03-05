import streamlit as st

from ui.utils import init_state
import logging
from ui.models import *
from ui.ui_components.attachments import get_attachment_component
from ui.services import get_supabase_manager,get_supabase_auth_service


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SidebarComponent:
    def __init__(self,):
        self.backend_service = get_supabase_manager()
        self.attachment_component = get_attachment_component()
        self.auth_service = get_supabase_auth_service()


    def llm_model_options(self, default_choice = None,expanded = False):
        llm_options = {
                    "openai": {
                        "fast": "gpt-4o-mini", 
                        "expert": "gpt-4o"
                    },
                    "google": {
                        "fast": "gemini-2.5-flash", 
                        "expert": "gemini-2.5-pro"
                    },
                    "qwen": {
                        "fast": "Qwen/Qwen3-VL-8B-Instruct", 
                        "expert": "Qwen/Qwen3.5-397B-A17B"
                    },
                    "meta" : {
                        "fast": "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                        "expert": "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"
                    },
                }

        # Agent type selector
        agent_type = st.radio(
            "Velg modell type:",
            ("fast", "expert"),
            horizontal=True,
            index=st.session_state.get('agent_type_index', 0) if st.session_state.get('agent_type_index') is not None else 0
        )
        with st.expander("Velg spesifikk modell (valgfritt)", expanded=expanded):
            llm_provider = st.radio(
                "Velg LLM leverandør:",
                ("openai", "google", "meta", "qwen"),
                #"claude"
                
                horizontal=True,
                index=st.session_state.get('llm_provider_index', 0) if st.session_state.get('llm_provider_index') is not None else 0
            )
        
            all_models = []
            for provider, types in llm_options.items():
                for _, model in types.items():
                    all_models.append(f"{provider} - {model}")
            custom_llm = st.selectbox("Velg spesifikk modell (valgfritt):",
                                      options = all_models,
                                      index = st.session_state.get('llm_model_index', default_choice) if st.session_state.get('llm_model_index') is not None else default_choice
            )
            if custom_llm:
                st.session_state.llm_model = custom_llm.replace(" - ","_")
                
            else:
                st.session_state.llm_model = llm_provider+ "_" + llm_options[llm_provider][agent_type]

        st.session_state.llm_model_index = all_models.index(custom_llm) if custom_llm else None
        st.session_state.llm_provider_index = ["openai", "google", "meta", "qwen"].index(st.session_state.llm_model.split("_")[0]) if st.session_state.llm_model.split("_")[0] in ["openai","google","qwen","meta"] else None
        st.session_state.agent_type_index = ["fast", "expert"].index(st.session_state.llm_model.split("_")[1]) if st.session_state.llm_model.split("_")[1] in ["fast", "expert"] else None
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

def get_sidebar_component() -> SidebarComponent:
    """Cached SidebarComponent instance"""
    return SidebarComponent()

