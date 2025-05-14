import os
import io
import re
import base64
import streamlit as st
from PIL import Image
from dotenv import load_dotenv
import openai
import fitz  # PyMuPDF

# Load environment variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    st.error("OpenAI API key not found in .env file.")
    st.stop()


def compress_image(image, max_size_mb=1):
    """
    Compress image to JPEG under max_size_mb
    """
    img_byte_arr = io.BytesIO()
    quality = 80
    while True:
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format="JPEG", quality=quality)
        if img_byte_arr.tell() <= max_size_mb * 1024 * 1024 or quality <= 10:
            break
        quality -= 5
    return img_byte_arr.getvalue()


def encode_image(image_bytes):
    """
    Encode image bytes to base64
    """
    return base64.b64encode(image_bytes).decode('utf-8')


def extract_invoice_number(text):
    match = re.search(r"Best Vendor:.*?Invoice\s+(\d+)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def main():
    st.title("Vendor Recommendation System")
    st.write("Upload invoice files (JPG, PNG, or PDF).")

    uploaded_files = st.file_uploader("Upload invoice files", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

    if uploaded_files and st.button("Analyze and Recommend Vendor"):
        image_prompts = []
        invoice_images = []  # store images per invoice

        for i, uploaded_file in enumerate(uploaded_files):
            try:
                uploaded_file.seek(0)
                file_bytes = uploaded_file.read()
                file_ext = uploaded_file.name.lower().split('.')[-1]

                if file_ext == "pdf":
                    doc = fitz.open(stream=file_bytes, filetype="pdf")
                    page = doc[0]  # only use first page
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("jpeg")
                    base64_img = encode_image(img_bytes)
                    image_prompts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
                    })
                    invoice_images.append(img_bytes)  # store uncompressed image bytes

                else:
                    image = Image.open(io.BytesIO(file_bytes))
                    compressed = compress_image(image)
                    base64_img = encode_image(compressed)
                    image_prompts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
                    })
                    invoice_images.append(compressed)

            except Exception as e:
                st.error(f"Error processing Invoice {i+1}: {e}")
                return

        # GPT-4o prompt
        system_prompt = (
            "You are a vendor evaluation assistant. The user has uploaded multiple invoices from different vendors. "
            "For each invoice:\n"
            "- Extract the vendor name\n"
            "- Extract the total price or amount\n"
            "- Provide a short reasoning\n\n"
            "Then clearly recommend the best vendor (Invoice 1, 2, etc.) and explain why."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": "Please analyze these invoices and respond like:\n\n"
                                         "Invoice 1:\nVendor: ...\nPrice: ...\nReason: ...\n\n"
                                         "Best Vendor: Invoice X – because ..."},
            ] + image_prompts}
        ]

        try:
            with st.spinner("Analyzing invoices"):
                response = openai.chat.completions.create(
                    model="gpt-4o-2024-08-06",
                    messages=messages,
                    max_tokens=2000,
                    temperature=0
                )

                result = response.choices[0].message.content.strip()
                st.success("✅ Recommendation:")
                st.markdown(result)

                # Identify best invoice number
                best_invoice_index = extract_invoice_number(result)
                if best_invoice_index:
                    img_bytes = invoice_images[best_invoice_index - 1]  # convert 1-based to 0-based index
                    image = Image.open(io.BytesIO(img_bytes))
                    image = image.resize((400, int(image.height * 400 / image.width)), Image.LANCZOS)
                    st.markdown("---")
                    st.markdown(f"📎 **Recommended Invoice (Invoice {best_invoice_index}):**")
                    st.image(image, use_column_width=False)

        except Exception as e:
            st.error(f"API Error: {e}")


if __name__ == "__main__":
    main()