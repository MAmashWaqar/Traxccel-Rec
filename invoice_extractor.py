import os
import base64
import io
import json
import fitz
import openai
import pandas as pd
from PIL import Image
import streamlit as st
from dotenv import load_dotenv

VERIFIED_INVOICES_FILE = 'verified_invoices.json'

def save_verified_invoices(verified_invoices):
    with open(VERIFIED_INVOICES_FILE, 'w') as f:
        json.dump(verified_invoices, f, indent=4)

def load_verified_invoices():
    if os.path.exists(VERIFIED_INVOICES_FILE):
        with open(VERIFIED_INVOICES_FILE, 'r') as f:
            return json.load(f)
    else:
        return []

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# File to persist verified invoice data
VERIFIED_JSON_PATH = "verified_invoices.json"

# === Utility Functions ===
def encode_image(image_bytes):
    return base64.b64encode(image_bytes).decode("utf-8")

def compress_image(image, max_size_mb=4):
    image = image.convert("RGB")
    img_byte_arr = io.BytesIO()
    quality = 95
    while True:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="JPEG", quality=quality)
        if img_byte_arr.tell() <= max_size_mb * 1024 * 1024 or quality <= 10:
            break
        quality -= 5
    return img_byte_arr.getvalue()

def extract_text_from_image(image_bytes):
    base64_image = encode_image(image_bytes)
    system_prompt = """
You are an expert in parsing financial documents and invoices. Your task is to extract structured information from invoices of varying formats...
(Return structured JSON under the categories: InvoiceDetails, VendorDetails, CutomerDetails, LineItems, ChargesSummary, Notes.)
"""
    user_prompt = """
Extract all relevant information from the following invoice text...
(As structured JSON in the specified six categories. Return empty strings for missing fields.)
"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]}
    ]
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-2024-08-06",
            messages=messages,
            max_tokens=4000,
            temperature=0
        )
        content = response.choices[0].message.content.strip()
        json_start = content.find("{")
        json_end = content.rfind("}")
        return json.loads(content[json_start:json_end + 1])
    except Exception as e:
        return {"error": str(e)}

def flatten_json(d, parent_key='', sep=' > '):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_json(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for idx, item in enumerate(v):
                if isinstance(item, dict):
                    items.extend(flatten_json(item, f"{new_key}[{idx}]", sep=sep).items())
                else:
                    items.append((f"{new_key}[{idx}]", item))
        else:
            items.append((new_key, v))
    return dict(items)

# === Screen: Invoice Extraction ===
def render_main_page():
    st.title("📄 Invoice Extractor")

    if "data" not in st.session_state:
        st.session_state.data = []
    if "extraction_complete" not in st.session_state:
        st.session_state.extraction_complete = False
    if "selected_view_idx" not in st.session_state:
        st.session_state.selected_view_idx = None

    uploaded_files = st.file_uploader("Upload PDF invoices", type=["pdf"], accept_multiple_files=True)

    if uploaded_files and st.button("Extract All"):
        st.session_state.data = []
        st.session_state.extraction_complete = False
        st.session_state.selected_view_idx = None

        total_pages = 0
        for file in uploaded_files:
            file.seek(0)
            total_pages += fitz.open(stream=file.read(), filetype="pdf").page_count
        progress = st.progress(0, text="Starting...")
        status_area = st.empty()
        count = 0

        with st.spinner("🔄 Extracting invoices..."):
            for uploaded_file in uploaded_files:
                filename = uploaded_file.name
                uploaded_file.seek(0)
                pdf_doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
                for page_num, page in enumerate(pdf_doc):
                    entry = {
                        "file": filename,
                        "page": page_num + 1,
                        "status": "Extracting...",
                        "image": None,
                        "json": None
                    }
                    st.session_state.data.append(entry)
                    status_area.table(pd.DataFrame(st.session_state.data)[["file", "page", "status"]])

                    image_bytes = page.get_pixmap(dpi=150).pil_tobytes(format="jpeg")
                    image_pil = Image.open(io.BytesIO(image_bytes))
                    compressed = compress_image(image_pil)

                    result = extract_text_from_image(compressed)

                    entry["status"] = "Done" if "error" not in result else "Failed"
                    entry["image"] = compressed
                    entry["json"] = result

                    status_area.table(pd.DataFrame(st.session_state.data)[["file", "page", "status"]])

                    count += 1
                    percent_complete = int((count / total_pages) * 100)
                    progress.progress(count / total_pages, text=f"Processing... {percent_complete}% completed")

        st.session_state.extraction_complete = True
        st.rerun()

    if st.session_state.extraction_complete:
        st.subheader("✅ View Extracted Pages")

        combined_rows = []
        for row in st.session_state.data:
            if isinstance(row["json"], dict):
                flat = flatten_json(row["json"])
                for k, v in flat.items():
                    combined_rows.append({
                        "File": row["file"],
                        "Page": row["page"],
                        "Field": k,
                        "Value": v
                    })

        if combined_rows:
            full_df = pd.DataFrame(combined_rows)
            st.download_button(
                label="📥 Download All Extracted Data (CSV)",
                data=full_df.to_csv(index=False).encode("utf-8"),
                file_name="all_invoices_extracted.csv",
                mime="text/csv"
            )

        for idx, row in enumerate(st.session_state.data):
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.markdown(f"**{row['file']} (Page {row['page']})**")
            col2.markdown(row["status"])
            if row["status"] == "Done":
                if col3.button("View", key=f"view_{idx}"):
                    st.session_state.selected_view_idx = idx
                    st.rerun()

            if st.session_state.selected_view_idx == idx:
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.image(row["image"], caption="Input Page", use_container_width=True)

                with col2:
                    if isinstance(row["json"], dict):
                        flat = flatten_json(row["json"])
                        df = pd.DataFrame(flat.items(), columns=["Field", "Value"])
                        st.dataframe(df, use_container_width=True)
                        csv_bytes = df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            label="📥 Download CSV for This Page",
                            data=csv_bytes,
                            file_name=f"{row['file'].replace('.pdf','')}_page_{row['page']}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.write(row["json"])

# === Screen: Procurement Review ===
def render_procurement_review():
    st.title("👨‍💼 Head of Procurement")

    if "data" not in st.session_state or not st.session_state.data:
        st.warning("No extracted data available. Please upload and extract invoices first.")
        return

    verified_invoices = load_verified_invoices()
    already_verified = {(v["file"], v["page"]) for v in verified_invoices}

    for idx, row in enumerate(st.session_state.data):
        key = (row["file"], row["page"])
        if row["status"] != "Done" or not isinstance(row["json"], dict) or key in already_verified:
            continue

        with st.expander(f"{row['file']} – Page {row['page']}"):
            col1, col2 = st.columns([1, 2])
            with col1:
                st.image(row["image"], caption="Invoice Page", use_container_width=True)

            verified_entry = {}
            with col2:
                st.subheader("🔍 Verify Fields")
                flat_data = flatten_json(row["json"])
                for field, value in flat_data.items():
                    new_val = st.text_input(f"{field}", value=value, key=f"{idx}_{field}")
                    verified_entry[field] = new_val

                if st.button("✅ Verify & Forward to Finance", key=f"verify_{idx}"):
                    verified_invoices.append({
                        "file": row["file"],
                        "page": row["page"],
                        "fields": verified_entry
                    })
                    save_verified_invoices(verified_invoices)
                    st.success("Verified and forwarded to Finance.")
                    st.rerun()

# === Screen: Finance Approval ===
def render_finance_approval():
    st.title("💰 Head of Finance")

    verified_invoices = load_verified_invoices()

    if not verified_invoices:
        st.info("No invoices forwarded from Procurement.")
        return

    updated_invoices = []
    for idx, invoice in enumerate(verified_invoices):
        approved = False
        with st.expander(f"{invoice['file']} – Page {invoice['page']}"):
            df = pd.DataFrame(invoice["fields"].items(), columns=["Field", "Value"])
            st.dataframe(df, use_container_width=True)

            if st.button("✅ Approve", key=f"approve_{idx}"):
                st.success("Invoice Approved ✅")
                approved = True

        # Only keep non-approved invoices
        if not approved:
            updated_invoices.append(invoice)

    # Save updated list after processing all approvals
    if len(updated_invoices) != len(verified_invoices):
        save_verified_invoices(updated_invoices)
        st.rerun()

# === Navigation ===
def run_invoice_extractor_app():
    screen = st.sidebar.radio("Select View", ["Invoice Extractor", "Head of Procurement", "Head of Finance"])

    if screen == "Invoice Extractor":
        render_main_page()
    elif screen == "Head of Procurement":
        render_procurement_review()
    elif screen == "Head of Finance":
        render_finance_approval()
