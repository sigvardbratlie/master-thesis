import streamlit as st
import uuid
import logging

from ui.models import UserDetails, CompanyDetails
from ui.services import get_supabase_manager, get_supabase_auth_service
from ui.utils import init_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_state()

db = get_supabase_manager()
auth_service = get_supabase_auth_service()

# ================== AUTH ==================
auth_service.restore_session()

if not auth_service.is_logged_in():
    auth_service.render_login_form()
    st.stop()

auth_service.save_token_to_url()
user_id = st.session_state.user_id

# ================== PAGE ==================
st.html("<div style='font-size: 3.5rem; line-height: 1;'>👤</div>")

title_row = st.container(horizontal=True, vertical_alignment="bottom")
with title_row:
    st.title("User Details", anchor=False, width="stretch")

""  # Spacer

# Load existing data
user_details = db.load_user_details(user_id)
companies = db.load_all_companies()

company_map = {c.company_id: c.company_name or c.company_id for c in companies}

# ================== USER DETAILS SECTION ==================
st.subheader("Your details", anchor=False)

# Determine current values
current_first = user_details.user_first_name if user_details else ""
current_last = user_details.user_last_name if user_details else ""
current_role = user_details.user_role if user_details else ""
current_company_id = user_details.company_id if user_details else None

# Build company selector options
company_options = ["-- No company --"] + [f"{name} ({cid[:8]}...)" for cid, name in company_map.items()]
company_ids = [None] + list(company_map.keys())

# Find current index
current_company_index = 0
if current_company_id and current_company_id in company_ids:
    current_company_index = company_ids.index(current_company_id)

with st.form("user_details_form"):
    col1, col2 = st.columns(2)
    with col1:
        first_name = st.text_input("First name", value=current_first or "")
    with col2:
        last_name = st.text_input("Last name", value=current_last or "")

    col3, col4 = st.columns(2)
    with col3:
        role = st.text_input("Role", value=current_role or "")
    with col4:
        selected_company_idx = st.selectbox(
            "Company",
            range(len(company_options)),
            format_func=lambda i: company_options[i],
            index=current_company_index,
        )

    ""  # Spacer

    submit_user = st.form_submit_button("Save user details", type="primary")

    if submit_user:
        selected_company_id = company_ids[selected_company_idx]
        updated = UserDetails(
            user_id=user_id,
            user_first_name=first_name or None,
            user_last_name=last_name or None,
            user_role=role or None,
            company_id=selected_company_id,
        )
        if db.upsert_user_details(updated):
            st.success("User details saved.")
            st.rerun()
        else:
            st.error("Could not save user details.")

# ================== COMPANY SECTION ==================
st.divider()
st.subheader("Company", anchor=False)

if current_company_id:
    company = db.load_company_details(current_company_id)
    if company:
        with st.form("edit_company_form"):
            col1, col2 = st.columns(2)
            with col1:
                edit_name = st.text_input("Company name", value=company.company_name or "")
            with col2:
                edit_vat = st.text_input("VAT number", value=company.company_vat_nr or "")

            ""  # Spacer

            submit_edit = st.form_submit_button("Update company", type="primary")

            if submit_edit:
                updated_company = CompanyDetails(
                    company_id=company.company_id,
                    company_name=edit_name or None,
                    company_vat_nr=edit_vat or None,
                )
                if db.upsert_company_details(updated_company):
                    st.success("Company updated.")
                    st.rerun()
                else:
                    st.error("Could not update company.")

with st.expander("Add new company", expanded=not companies):
    with st.form("new_company_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_company_name = st.text_input("Company name")
        with col2:
            new_company_vat = st.text_input("VAT number")

        ""  # Spacer

        submit_company = st.form_submit_button("Save company", type="primary")

        if submit_company:
            if not new_company_name:
                st.warning("Company name is required.")
            else:
                new_company = CompanyDetails(
                    company_id=str(uuid.uuid4()),
                    company_name=new_company_name,
                    company_vat_nr=new_company_vat or None,
                )
                if db.upsert_company_details(new_company):
                    st.success(f"Company '{new_company_name}' created.")
                    st.rerun()
                else:
                    st.error("Could not save company.")
