"""
Velozählungen Zürich — Einstiegspunkt & Navigation
"""

import streamlit as st

st.set_page_config(page_title="Velozählungen Zürich", layout="wide")

pg = st.navigation([
    st.Page("app_velo.py", title="Velo-Analyse", icon="🚲"),
    st.Page("pages/velo_vs_miv.py", title="Velo vs. MIV", icon="🚗"),
])
pg.run()
