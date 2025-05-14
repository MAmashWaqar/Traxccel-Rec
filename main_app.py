import streamlit as st
from invoice_extractor import run_invoice_extractor_app
from vendor_recommender import main as run_vendor_recommender

# ✅ Set this ONCE and FIRST
st.set_page_config(page_title="AI Toolkit", layout="wide")

# Sidebar navigation
st.sidebar.title("🧭 Navigation")
selected_tool = st.sidebar.selectbox("Choose a tool", ["Invoice Extractor", "Vendor Recommender"])

# Routing
if selected_tool == "Invoice Extractor":
    run_invoice_extractor_app()

elif selected_tool == "Vendor Recommender":
    run_vendor_recommender()
