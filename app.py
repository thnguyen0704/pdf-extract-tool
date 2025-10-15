import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Extract Invoice Data from Multiple PDF Files", layout="centered")
st.title("Extract Invoice Data from Multiple PDF Files")

uploaded_files = st.file_uploader("Upload one or more PDF files", type="pdf", accept_multiple_files=True)
invoice_input = st.text_area("Enter Invoice Numbers (one per line)", height=200)

if uploaded_files and invoice_input:
    invoice_list = [inv.strip() for inv in invoice_input.splitlines() if inv.strip()]
    invoice_status = {inv: {
        "Invoice Number": inv,
        "File Name": None,
        "PDF Page": None,
        "Carton Number": None,
        "Quantity": None,
        "Total Amount": None,
        "Reference PO": None,
        "PO#": None,
        "Booking Number": None,
        "Material #": None,
        "PO Line Item Seq. #": None,
        "VGM Link": None
    } for inv in invoice_list}

    file_buffers = [(f.name, f.read()) for f in uploaded_files]

    for file_name, file_bytes in file_buffers:
        with fitz.open(stream=BytesIO(file_bytes), filetype="pdf") as doc:
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                lines = text.splitlines()

                for invoice in invoice_list:
                    # FORWARDER'S CERTIFICATE RECEIPT
                    if "FORWARDER'S CERTIFICATE RECEIPT" in text:
                        if re.search(rf"\b{re.escape(invoice)}\b", text):
                            if not invoice_status[invoice]["File Name"]:
                                invoice_status[invoice]["File Name"] = file_name
                                invoice_status[invoice]["PDF Page"] = page_num + 1

                    # BOOKING
                    if "KN BOOKING CONFIRMATION" in text:
                        if re.search(rf"\b{re.escape(invoice)}\b", text):
                            vgm_links = re.findall(r"https://vgm\.[^\s]+", text)
                            if vgm_links:
                                joined_links = ", ".join(sorted(set(vgm_links)))
                                inv_data = invoice_status[invoice]
                                if not inv_data["VGM Link"]:
                                        inv_data["VGM Link"] = joined_links
                                        invoice_status[invoice]["File Name"] = file_name
                                        invoice_status[invoice]["PDF Page"] = page_num + 1
                                    

                    # FACTORY COMMERCIAL INVOICE
                    if "Factory Commercial Invoice" in text and invoice in text:
                        inv_data = invoice_status[invoice]

                        # Set file name and page only once
                        if not inv_data["File Name"]:
                            inv_data["File Name"] = file_name
                            inv_data["PDF Page"] = page_num + 1

                        # Extract standard fields
                        patterns = {
                            "Carton Number": r"Total Number of Cartons[:\s]*([\d,]+)",
                            "Total Amount": r"Total Amount[:\s]*([\d,]+\.\d{2})",
                            "Reference PO": r"Reference PO#?:\s*(\d{10})",
                            "PO#": r"(?<![A-Za-z0-9])(\d{10})(?!\d)"
                            "Booking Number": r"Booking Number:\s*([A-Z0-9]+)"
                        }
                        for field, pattern in patterns.items():
                            match = re.search(pattern, text)
                            if match and not inv_data[field]:
                                inv_data[field] = match.group(1)

                        if inv_data["PO#"] == inv_data["Reference PO"]:
                            inv_data["PO#"] = None

                        # Extract Material #
                        material_pattern = re.compile(r'\b(?:[A-Z]{2}|\d{2})\d{4}-\d{3}\b')
                        new_materials = []
                        for line in lines:
                            matches = material_pattern.findall(line)
                            if matches:
                                new_materials.extend(matches)
                        if new_materials:
                            existing_materials = inv_data["Material #"].split(", ") if inv_data["Material #"] else []
                            all_materials = sorted(set(existing_materials + new_materials))
                            inv_data["Material #"] = ", ".join(all_materials)

                        # Extract Quantity line by line
                        for line in lines:
                            match_qty = re.search(r"Total Invoice Quantity[:\s]*([\d,]+)", line, re.IGNORECASE)
                            if match_qty:
                                inv_data["Quantity"] = match_qty.group(1)
                                break

                        # Extract PO Line Item Seq. # (5 digits starting with 0, standalone, exclude 01000)
                        po_line_pattern = re.compile(r"\b0\d{4}\b")
                        new_po_seqs = []
                        for line in lines:
                            matches = po_line_pattern.findall(line)
                            if matches:
                                new_po_seqs.extend(matches)

                        # Remove "01000"
                        filtered_po_seqs = [seq for seq in new_po_seqs if seq != "01000"]

                        if filtered_po_seqs:
                            existing_seqs = inv_data["PO Line Item Seq. #"].split(", ") if inv_data["PO Line Item Seq. #"] else []
                            all_seqs = sorted(set(existing_seqs + filtered_po_seqs))
                            inv_data["PO Line Item Seq. #"] = ", ".join(all_seqs)

    df = pd.DataFrame(invoice_status.values())

    st.success(f"Done! Found {df['File Name'].notna().sum()} / {len(df)} invoice(s).")
    st.dataframe(df)

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Result as CSV",
        data=csv_data,
        file_name="invoice_data.csv",
        mime="text/csv"
    )
