import streamlit as st
import requests
import logging
from typing import Optional
from models import SessionHistoryResponse, SessionInfo

logger = logging.getLogger(__name__)


class SessionService:
    """Handles session loading and management"""

    def __init__(self, backend_url: str, user_id: str):
        self.backend_url = backend_url
        self.user_id = user_id

    def load_session_history(self, session_id: str) -> Optional[SessionHistoryResponse]:
        """
        Load session history from backend.

        Args:
            session_id: Session ID to load

        Returns:
            SessionHistoryResponse if successful, None otherwise
        """
        try:
            response = requests.get(
                f'{self.backend_url}/load-session-history/{self.user_id}/{session_id}'
            )
            response.raise_for_status()

            if not response:
                st.error(f'Error when loading chat history: {response}')
                return None

            return SessionHistoryResponse(**response.json())

        except requests.exceptions.RequestException as e:
            st.error(f'Error when loading chat history: {e}')
            logger.error(f"Failed to load session history: {e}")
            return None

    @st.cache_data(show_spinner=False)
    def load_user_sessions(_self, domain: str) -> list[SessionInfo]:
        """
        Load all user sessions for a given domain.

        Args:
            domain: Domain to filter sessions (e.g., "company")

        Returns:
            List of SessionInfo objects, empty list if error
        """
        try:
            response = requests.get(
                f'{_self.backend_url}/load-user-sessions/{_self.user_id}/{domain}'
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
