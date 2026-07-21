"""
Generic PDF -> Excel extractor (Streamlit app)

Works with ANY batch of structurally-similar PDFs (invoices, tax returns,
applications, certificates, statements, etc.) - not tied to one form type.

Workflow:
1. Upload one or more PDFs (same layout/template as each other).
2. Each PDF is parsed into a flat "label -> value" JSON using
   generic_pdf_extractor.py (reads tables and "Label: Value" style lines).
3. Review the extracted keys for this batch (they depend entirely on the
   PDF's own labels - a new PDF template will surface different keys,
   no code changes needed).
4. Upload a mapping Excel with two columns:
      Column A = desired output column header (name it whatever you like)
      Column B = the exact JSON key to pull the value from
   (Download a ready-made starter mapping straight from your own extracted
   keys using the button in step 3.)
5. Click "Generate Output Excel" -> one row per uploaded PDF, columns as
   defined in the mapping file. Missing/unmatched keys are filled with 0.
"""

import io

import pandas as pd
import streamlit as st

from generic_pdf_extractor import extract_pdf_to_json

st.set_page_config(page_title="PDF -> Excel Extractor", layout="wide")
st.title("PDF -> Excel Extractor")
st.caption("Generic tool: works with any batch of similarly-formatted PDFs — invoices, returns, forms, certificates, etc.")

st.markdown(
    """
    **Steps:** 1) Upload PDFs &nbsp;→&nbsp; 2) Review extracted fields &nbsp;→&nbsp;
    3) Upload a mapping Excel (Output Column Name | JSON Key) &nbsp;→&nbsp; 4) Download consolidated Excel.
    """
)

# ---------------------------------------------------------------------------
# Step 1: Upload PDFs
# ---------------------------------------------------------------------------
st.header("1. Upload PDF(s)")
pdf_files = st.file_uploader(
    "Upload one or more PDFs (same layout/template as each other)",
    type=["pdf"],
    accept_multiple_files=True,
)

extracted = {}  # filename -> flat dict
if pdf_files:
    for f in pdf_files:
        try:
            data = extract_pdf_to_json(io.BytesIO(f.read()), extra_meta={"file_name": f.name})
            extracted[f.name] = data
        except Exception as e:
            st.error(f"Failed to parse {f.name}: {e}")

    st.success(f"Parsed {len(extracted)} file(s).")

    # ---------------------------------------------------------------------
    # Step 2: Review extracted fields
    # ---------------------------------------------------------------------
    st.header("2. Review extracted fields")
    st.caption(
        "Field names come straight from labels found in the PDF. Complex tables with "
        "wrapped/multi-line headers can produce imperfect column names — check the "
        "value next to each key if a name looks unclear."
    )

    with st.expander("Preview extracted data per file", expanded=False):
        preview_file = st.selectbox("Choose a file to preview", list(extracted.keys()))
        st.json(extracted[preview_file])

    all_keys = sorted({k for d in extracted.values() for k in d.keys()})
    st.write(f"**{len(all_keys)} unique fields found across {len(extracted)} file(s):**")
    keys_df = pd.DataFrame(
        {
            "json_key": all_keys,
            "example_value": [extracted[list(extracted.keys())[0]].get(k, "") for k in all_keys],
        }
    )
    st.dataframe(keys_df, use_container_width=True, height=300)

    # Starter mapping built directly from this batch's own keys, so it
    # always matches whatever PDFs were just uploaded.
    starter_map = pd.DataFrame({"Output Column Name": all_keys, "JSON Key": all_keys})
    starter_buf = io.BytesIO()
    starter_map.to_excel(starter_buf, index=False)
    st.download_button(
        "Download starter mapping Excel (all fields, edit as needed)",
        data=starter_buf.getvalue(),
        file_name="starter_mapping.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ---------------------------------------------------------------------------
# Step 3: Upload mapping Excel
# ---------------------------------------------------------------------------
st.header("3. Upload mapping Excel")
st.caption("Two columns required — Col A: output column header, Col B: JSON key (copy from the field list above).")
mapping_file = st.file_uploader("Upload mapping Excel (.xlsx)", type=["xlsx"], key="mapping")

mapping_df = None
if mapping_file:
    mapping_df = pd.read_excel(mapping_file, usecols=[0, 1])
    mapping_df.columns = ["output_column", "json_key"]
    mapping_df = mapping_df.dropna(subset=["output_column"])
    st.dataframe(mapping_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Step 4: Generate output
# ---------------------------------------------------------------------------
st.header("4. Generate output Excel")

if extracted and mapping_df is not None:
    if st.button("Generate Output Excel", type="primary"):
        rows = []
        for fname, data in extracted.items():
            row = {}
            for _, m in mapping_df.iterrows():
                col_name = str(m["output_column"]).strip()
                json_key = str(m["json_key"]).strip()
                val = data.get(json_key)
                row[col_name] = val if val not in (None, "") else 0
            rows.append(row)

        out_df = pd.DataFrame(rows)
        st.dataframe(out_df, use_container_width=True)

        out_buf = io.BytesIO()
        with pd.ExcelWriter(out_buf, engine="openpyxl") as writer:
            out_df.to_excel(writer, index=False, sheet_name="Extracted Data")
        st.download_button(
            "Download Output Excel",
            data=out_buf.getvalue(),
            file_name="extracted_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info("Upload PDF(s) and a mapping Excel above to enable output generation.")
