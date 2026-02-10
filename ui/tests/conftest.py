import pytest
from unittest.mock import MagicMock, patch
import sys

# Mock streamlit secrets BEFORE any imports happen
import streamlit as st
st.secrets._secrets = {
    "SUPABASE_URL": "http://test-supabase-url.com",
    "SUPABASE_KEY": "test-supabase-key"
}

# Mock session_state
if not hasattr(st.session_state, 'user_id'):
    st.session_state.user_id = "test-user-123"
if not hasattr(st.session_state, 'session_id'):
    st.session_state.session_id = "test-session-456"
