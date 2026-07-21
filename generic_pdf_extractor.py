"""
Generic PDF -> flat JSON (label/value) extractor.

Not tied to any specific form (GST, invoice, application, etc). Works on
any PDF that has a text layer, by pulling:
  1. Table rows -> "label" / "label - column_header" style keys
  2. Loose "Label: Value" style lines outside tables

Designed to be re-usable across completely different PDF layouts/schemas.
Whatever fields exist in a given batch of PDFs, this surfaces them as a
flat dict of key -> value so a user-supplied mapping file can pick and
rename whichever fields they care about.
"""
import re

import pdfplumber

# Stray single-character watermark lines seen in some portal-generated
# PDFs (e.g. a diagonal "FILED"/"DRAFT" stamp whose letters land on their
# own line inside table cells). Harmless to strip generically: a real
# table cell is essentially never a bare single uppercase letter.
_STRAY_WATERMARK_RE = re.compile(r"^[A-Z]$")


def _clean_cell(text):
    """Join a multi-line cell into one string, dropping stray single-letter
    watermark lines and re-joining numbers that wrapped mid-decimal
    (e.g. '6540867.\\n00' -> '6540867.00')."""
    if text is None:
        return ""
    lines = [l for l in text.split("\n")]
    lines = [l for l in lines if not _STRAY_WATERMARK_RE.match(l.strip())]

    merged = []
    i = 0
    while i < len(lines):
        cur = lines[i].strip()
        if (
            i + 1 < len(lines)
            and re.match(r"^-?[\d,]*\.$", cur)
            and re.match(r"^\d+$", lines[i + 1].strip())
        ):
            merged.append(cur + lines[i + 1].strip())
            i += 2
        else:
            merged.append(cur)
            i += 1
    return " ".join(m for m in merged if m).strip()


def _to_value(text):
    """Best-effort typing: number if it looks numeric, else the cleaned string.
    '-' / blank -> None (caller decides how to fill, e.g. 0)."""
    if text is None:
        return None
    v = text.strip()
    if v in ("", "-", "–"):
        return None
    v_num = v.replace(",", "")
    try:
        if re.match(r"^-?\d+(\.\d+)?$", v_num):
            f = float(v_num)
            return int(f) if f.is_integer() and "." not in v_num else f
    except ValueError:
        pass
    return v


def _add_key(data, key, value):
    key = key.strip()
    if not key:
        return
    if key in data:
        # collision on a plain label -> keep first, caller will have
        # already namespaced repeat tables before calling this for those
        return
    data[key] = value


def extract_pdf_to_json(path_or_buffer, extra_meta=None):
    """Parse any text-layer PDF into a flat dict of label -> value.

    path_or_buffer: file path (str) or file-like object (e.g. BytesIO from
    a Streamlit upload).
    extra_meta: optional dict merged into the result as-is (e.g. file_name).
    """
    data = {}
    seen_labels = set()

    with pdfplumber.open(path_or_buffer) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            for table_idx, table in enumerate(tables):
                if not table or not table[0]:
                    continue

                n_cols = max(len(r) for r in table if r)

                if n_cols <= 2:
                    # Simple "label / value" style table (most form headers,
                    # e.g. "GSTIN | 24AADCT..." or "Invoice No | INV-001")
                    for row in table:
                        if not row or row[0] is None:
                            continue
                        label = _clean_cell(row[0])
                        if not label:
                            continue
                        value = _to_value(_clean_cell(row[1])) if len(row) > 1 else None
                        key = label
                        if key in seen_labels:
                            key = f"p{page_idx+1}_t{table_idx+1} | {label}"
                        seen_labels.add(label)
                        _add_key(data, key, value)
                    continue

                # Multi-column table: row 0 is the header ONLY if it looks
                # like column titles (mostly non-numeric). Tables that
                # continue across a page break repeat no header row -
                # their first row is real data, so treat all rows as data
                # and fall back to generic column names in that case.
                first_row_cells = [_clean_cell(c) if c else "" for c in table[0][1:]]
                looks_like_header = all(
                    _to_value(c) is None or isinstance(_to_value(c), str)
                    for c in first_row_cells
                ) and any(c for c in first_row_cells)

                if looks_like_header:
                    header = [_clean_cell(c) if c else "" for c in table[0]]
                    data_rows = table[1:]
                else:
                    header = [f"col{i}" for i in range(len(table[0]))]
                    data_rows = table

                for row in data_rows:
                    if not row or row[0] is None:
                        continue
                    row_label = _clean_cell(row[0])
                    if not row_label:
                        continue
                    for col_idx in range(1, len(row)):
                        col_header = header[col_idx] if col_idx < len(header) else f"col{col_idx}"
                        base_key = f"{row_label} - {col_header}".strip(" -")
                        value = _to_value(_clean_cell(row[col_idx]))
                        key = base_key
                        if key in seen_labels:
                            key = f"p{page_idx+1}_t{table_idx+1} | {base_key}"
                        seen_labels.add(base_key)
                        _add_key(data, key, value)

            # Loose "Label: Value" lines outside of any bordered table
            text = page.extract_text() or ""
            for line in text.split("\n"):
                m = re.match(r"^\s*([A-Za-z][A-Za-z0-9 /_&().,'-]{2,60}?)\s*:\s*(.+?)\s*$", line)
                if m:
                    label, value = m.group(1).strip(), m.group(2).strip()
                    if label and value and label not in seen_labels:
                        seen_labels.add(label)
                        _add_key(data, label, _to_value(value))

    if extra_meta:
        data.update(extra_meta)

    return data


if __name__ == "__main__":
    import json
    import sys

    for f in sys.argv[1:]:
        print("====", f)
        print(json.dumps(extract_pdf_to_json(f), indent=2, default=str))
