import json
import pandas as pd
import streamlit as st
from utils import load_custom_css
from widgets.company_widget import company_dashboard

load_custom_css()

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

company_json = st.session_state.get("company_data")
industry_json = st.session_state.get("industry_data")

if not company_json:
    st.warning("Ingen firmadata tilgjengelig. Still et spørsmål om et selskap først.")
else:
    try:
        comp_rows = json.loads(company_json) if isinstance(company_json, str) else company_json
        df_company = pd.DataFrame(comp_rows) if isinstance(comp_rows, list) else pd.DataFrame()
    except Exception as e:
        st.error(f'Kunne ikke lese firmadata: {e}')
        df_company = pd.DataFrame()

    df_industry = pd.DataFrame()
    if industry_json:
        try:
            ind_rows = json.loads(industry_json) if isinstance(industry_json, str) else industry_json
            if isinstance(ind_rows, list):
                df_industry = pd.DataFrame(ind_rows)
        except Exception as e:
            st.warning(f'Kunne ikke lese bransjedata: {e}')

    if not df_company.empty:
        company_dashboard(df_company, industry_df=df_industry)
    else:
        st.error('Firmadata mangler eller er tom.')
