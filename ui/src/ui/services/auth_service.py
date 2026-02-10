import streamlit as st
import logging
from supabase import create_client

logger = logging.getLogger(__name__)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

class SupabaseAuthService:
    """Authentication service using Supabase"""
    
    
    def __init__(self):
        self._client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    @property
    def client(self):
        return self._client


    def login(self, email: str, password: str) -> bool:
        """Login with email/password via Supabase"""
        try:
            supabase = self.client
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if response.user and response.session:
                # Store in session state
                st.session_state.user_id = response.user.id
                st.session_state.user_email = response.user.email
                st.session_state.user_name = response.user.user_metadata.get("name", email)
                st.session_state.access_token = response.session.access_token
                st.session_state.refresh_token = response.session.refresh_token
                st.session_state._auth_initialized = True

                self._load_user_details(response.user.id)
                logger.info(f"User logged in: {email}")
                return True
        except Exception as e:
            logger.error(f"Login failed: {e}")
            st.error(f"Login feilet: {e}")
        return False


    def restore_session(self,) -> bool:
        """Restore session from refresh token in URL"""
        # Already have a session
        if st.session_state.get("_auth_initialized"):
            return True

        refresh_token = st.query_params.get("rt")
        if not refresh_token:
            return False

        try:
            supabase = self.client
            response = supabase.auth.refresh_session(refresh_token)

            if response.user and response.session:
                st.session_state.user_id = response.user.id
                st.session_state.user_email = response.user.email
                st.session_state.user_name = response.user.user_metadata.get("name", response.user.email)
                st.session_state.access_token = response.session.access_token
                st.session_state.refresh_token = response.session.refresh_token
                st.session_state._auth_initialized = True

                # Update token in URL if it changed
                new_token = response.session.refresh_token
                if new_token != refresh_token:
                    st.query_params["rt"] = new_token

                self._load_user_details(response.user.id)
                logger.info(f"Session restored for: {response.user.email}")
                return True
        except Exception as e:
            logger.warning(f"Could not restore session: {e}")
            # Clear invalid token from URL
            st.query_params.clear()

        return False


    def save_token_to_url(self,):
        """Save refresh token to URL - call this AFTER page is rendered"""
        if st.session_state.get("refresh_token"):
            current_rt = st.query_params.get("rt")
            new_rt = st.session_state.refresh_token
            if current_rt != new_rt:
                st.query_params["rt"] = new_rt


    def logout(self,):
        """Logout user"""
        try:
            supabase = self.client
            supabase.auth.sign_out()
        except:
            pass

        # Clear session state
        for key in ["user_id", "user_email", "user_name", "access_token", "refresh_token", "_auth_initialized"]:
            if key in st.session_state:
                del st.session_state[key]

        # Clear URL
        st.query_params.clear()


    def _load_user_details(self, user_id: str):
        """Load user_details from Supabase and store first/last name in session state"""
        try:
            result = self._client.table("user_details").select("user_first_name, user_last_name").eq("user_id", user_id).execute()
            if result.data:
                row = result.data[0]
                st.session_state.user_first_name = row.get("user_first_name")
                st.session_state.user_last_name = row.get("user_last_name")
        except Exception as e:
            logger.warning(f"Could not load user details: {e}")
            #print(user_id)

    def is_logged_in(self,) -> bool:
        """Check if user is logged in"""
        return st.session_state.get("user_id") is not None


    def render_login_form(self,):
        """Render login form"""
        col1, col2, col3 = st.columns([1, 1.5, 1])
        with col2:
            st.html("<div style='font-size: 3.5rem; line-height: 1; text-align: center; margin-top: 6rem;'>⚖️</div>")
            st.title("Logg inn", anchor=False)
            ""  # Spacer

            email = st.text_input("E-post", key="login_email")
            password = st.text_input("Passord", type="password", key="login_password")

            ""  # Spacer

            if st.button("Logg inn", use_container_width=True, type="primary"):
                if email and password:
                    if self.login(email, password):
                        self.save_token_to_url()
                        st.rerun()
                else:
                    st.warning("Fyll inn e-post og passord")

@st.cache_resource
def get_supabase_auth_service():
    return SupabaseAuthService()