import streamlit as st
import requests
import logging
from ui.models import SessionHistoryResponse, SessionInfo

logger = logging.getLogger(__name__)


class SessionService:
    """Handles session loading and management"""

    def __init__(self, backend_url: str, user_id: str, access_token: str):
        self.backend_url = backend_url
        self.user_id = user_id
        self.access_token = access_token
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Authorization': f'Bearer {access_token}'
        }

    # ================== SESSION METHODS ==================
    
    def load_session_history(_self, session_id: str) -> SessionHistoryResponse | None:
        """
        Load session history from backend.

        Args:
            session_id: Session ID to load

        Returns:
            SessionHistoryResponse if successful, None otherwise
        """
        try:
            response = requests.get(
                f'{_self.backend_url}/load-session-history/{session_id}',
                headers=_self.headers,
            )
            response.raise_for_status()

            if not response:
                st.error(f'Error when loading session history: {response}')
                return None

            return SessionHistoryResponse(**response.json())

        except requests.exceptions.RequestException as e:
            #st.error(f'Error when loading session history: {e}')
            logger.error(f"Failed to load session history: {e}")
            return None

    @st.cache_data(show_spinner=False)
    def load_user_sessions(_self,) -> list[SessionInfo]:
        """
        Load all user sessions.

        Args:

        Returns:
            List of SessionInfo objects, empty list if error
        """
        try:
            response = requests.get(
                f'{_self.backend_url}/load-user-sessions',
                headers=_self.headers,
            )
            response.raise_for_status()

            if not response:
                st.error(f'Error when loading user sessions: {response}')
                return []

            return [SessionInfo(**s) for s in response.json()]

        except requests.exceptions.RequestException as e:
            st.error(f'Error when loading user sessions: {e}')
            logger.error(f"Failed to load user sessions: {e}")
            return []

    # ================== PROJECT METHODS ==================

    #@st.cache_data(show_spinner=False)
    def load_projects(_self, ) -> SessionHistoryResponse | None:
        """
        Load session history from backend.
        """
        try:
            response = requests.get(
                f'{_self.backend_url}/load-projects',
                headers=_self.headers,
            )
            response.raise_for_status()

            if not response:
                st.error(f'Error when loading projects: {response}')
                return None

            return response.json()

        except requests.exceptions.RequestException as e:
            st.error(f'Error when loading projects: {e}')
            logger.error(f"Failed to load projects: {e}")
            return None

    #@st.cache_data(show_spinner=False)
    def load_project_sessions(_self, ) -> list[SessionInfo]:
        """
        Load project sessions for the current project.

        Args:

        Returns:
            List of SessionInfo objects, empty list if error
        """
        try:
            response = requests.get(
                f'{_self.backend_url}/load-project-sessions/{st.session_state.project_id}',
                headers=_self.headers,
            )
            response.raise_for_status()

            if not response:
                st.error(f'Error when loading project sessions: {response}')
                return []

            return [SessionInfo(**s) for s in response.json()]

        except requests.exceptions.RequestException as e:
            #st.error(f'Error when loading project sessions: {e}')
            logger.error(f"Failed to load project sessions: {e}")
            return []
    
    def load_project(_self,) -> dict | None:
        """
        Load factsheet for a given project.
        """
        try:
            response = requests.get(
                f'{_self.backend_url}/load-project/{st.session_state.project_id}',
                headers=_self.headers,
            )
            response.raise_for_status()

            if not response:
                st.error(f'Error when loading factsheet: {response}')
                return None

            return response.json()

        except requests.exceptions.RequestException as e:
            st.error(f'Error when loading factsheet: {e}')
            logger.error(f"Failed to load factsheet: {e}")
            return None
        
@st.cache_resource
def get_session_service(backend_url: str, user_id: str, access_token: str) -> SessionService:
    """Cached SessionService instance"""
    return SessionService(backend_url, user_id, access_token)