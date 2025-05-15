import streamlit as st
from invoice_extractor import run_invoice_extractor_app
from vendor_recommender import main as run_vendor_recommender

# ✅ Set page config first
st.set_page_config(page_title="AI Toolkit", layout="wide")

# Sidebar navigation
st.sidebar.title("🧭 Navigation")

# Add a placeholder option first
tool_options = ["-- Select a Tool --", "Invoice Extractor", "Vendor Recommender"]
selected_tool = st.sidebar.selectbox("Choose a tool", tool_options)

# Only run the selected tool if a valid one is chosen
if selected_tool == "Invoice Extractor":
    run_invoice_extractor_app()

elif selected_tool == "Vendor Recommender":
    run_vendor_recommender()

else:
    st.markdown("### 👈 Please select a tool from the sidebar to get started.")
