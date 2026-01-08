import streamlit as st
import requests
import logging
from typing import Optional
from ui.models import StreamlitUserInfo, TokenResponse

logger = logging.getLogger(__name__)


class AuthService:
    """Handles authentication with backend"""

    def __init__(self, backend_url: str):
        self.backend_url = backend_url

    def authenticate_with_backend(self) -> bool:
        """
        Authenticates with backend after Streamlit Google OAuth login.
        Sends user info from st.user to backend to get internal JWT access token.

        Returns:
            True if authentication successful, False otherwise
        """
        # Check if logged in via Streamlit but missing backend token
        if st.user.is_logged_in and (
            "access_token" not in st.session_state or
            st.session_state.access_token is None
        ):
            try:
                user_data = StreamlitUserInfo(
                    sub=st.user.sub,
                    email=st.user.email,
                    name=st.user.name,
                    picture=st.user.picture
                )

                # Call backend to exchange Google credentials for JWT
                response = requests.post(
                    f"{self.backend_url}/token-from-streamlit",
                    json=user_data.model_dump()
                )
                response.raise_for_status()

                # Parse and store token response
                token_response = TokenResponse(**response.json())

                st.session_state.access_token = token_response.access_token
                st.session_state.token_type = token_response.token_type
                st.session_state.user_id = token_response.user_id
                st.session_state.user_name = token_response.user_name

                logger.info(f"Successfully authenticated user {st.user.email} with backend.")
                return True

            except requests.exceptions.RequestException as e:
                st.error(f"Kunne ikke autentisere mot backend: {e}")
                logger.error(f"Authentication failed: {e}")
                st.logout()
                return False

        # If we already have a token, all good
        elif "access_token" in st.session_state and st.session_state.access_token is not None:
            return True

        return False
