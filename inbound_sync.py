"""Shared inbound-shipment writers — used by BOTH the morning pipeline (main.py) and
the web app's "update now" button (streamlit_app.py).

Kept dependency-light on purpose (no rich/alerts imports) so the cloud app can import
it: just config + gspread objects passed in.

  write_inbound_shipments_tab(sh, rows)  -> the 'Inbound Shipments' tab in the dashboard
  write_fba_ids_to_sky(client, rows)     -> the 'FBA Shipments (auto)' column on Sky's sheet

`rows` = list from fetch_nineyard.get_inbound_shipments().
"""
import config


def _get_or_create_ws(spreadsheet, title, rows=200, cols=30):
    from gspread.exceptions import WorksheetNotFound
    try:
        return spreadsheet.worksheet(title)
    except WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def write_inbound_shipments_tab(spreadsheet, ship_rows) -> None:
    """Write a per-(shipment, SKU) breakdown of what's on the way to FBA, from NineYard.
    The web app reads this tab to power the 'units on the way' drop-down with clickable
    Seller Central shipment links.

    Only SKUs that are part of the China reorder dashboard are kept — the 'App Data'
    tab IS that set — so unrelated (non-China) 9Yards shipments are dropped."""
    from datetime import datetime, timezone
    updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        china_skus = {str(r.get("SKU", "")).strip()
                      for r in spreadsheet.worksheet("App Data").get_all_records()}
        china_skus.discard("")
    except Exception:
        china_skus = set()
    if china_skus:
        ship_rows = [r for r in (ship_rows or []) if str(r.get("sku", "")).strip() in china_skus]
    headers = ["SKU", "Units on the way", "Shipment ID", "9Yards ID", "Shipment name",
               "Status", "Type", "Account", "Updated"]
    values = [headers]
    for r in sorted(ship_rows or [], key=lambda x: (str(x.get("amazon_shipment_id", "")), str(x.get("sku", "")))):
        values.append([
            r.get("sku", ""), int(r.get("qty", 0)), r.get("amazon_shipment_id", ""),
            r.get("shipment_header_id", ""),
            r.get("shipment_name", ""), r.get("status", ""), r.get("type", ""),
            r.get("account", ""), updated,
        ])
    ws = _get_or_create_ws(spreadsheet, "Inbound Shipments", rows=max(200, len(values) + 10), cols=len(headers))
    ws.clear()
    ws.update(values, range_name="A1", value_input_option="RAW")
    sid = ws.id
    spreadsheet.batch_update({"requests": [
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                        "fields": "userEnteredFormat.textFormat"}},
        {"updateSheetProperties": {"properties": {"sheetId": sid,
                                                  "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
    ]})


def write_fba_ids_to_sky(client, ship_rows) -> int:
    """Traceability column on Sky's sheet: for every SKU, which FBA shipment ID(s) its
    in-transit units are under (from 9Yards), e.g. 'FBA19FXCC0LB ×300 · FBA19GD41VH9 ×40'.
    Writes/reuses a column headed 'FBA Shipments (auto)' on each tab of Sky's sheet —
    an auto column we own; nothing of Sky's is touched. Cells clear when units land.
    Returns the number of SKUs annotated."""
    _STATUS_SHORT = {"WORKING": "working", "SHIPPED": "shipped", "IN_TRANSIT": "in transit",
                     "RECEIVING": "receiving", "DELIVERED": "delivered"}

    # {sku: "FBAID ×qty (status) · FBAID ×qty (status)"}
    by_sku = {}
    for r in (ship_rows or []):
        sku = str(r.get("sku", "")).strip()
        fba = str(r.get("amazon_shipment_id", "")).strip()
        if not sku or not fba:
            continue
        stat = _STATUS_SHORT.get(str(r.get("status", "")).strip().upper(), "")
        by_sku.setdefault(sku, []).append(f"{fba} ×{int(r.get('qty', 0)):,}" + (f" ({stat})" if stat else ""))
    text_by_sku = {k: "  ·  ".join(v) for k, v in by_sku.items()}

    def col_letter(i):  # 0-based index -> A1 letter
        s = ""
        i += 1
        while i:
            i, rem = divmod(i - 1, 26)
            s = chr(65 + rem) + s
        return s

    sh = client.open_by_key(config.SKY_SHEET_ID)
    annotated = 0
    for ws in sh.worksheets():
        vals = ws.get_all_values()
        if len(vals) < 3:
            continue
        hdr = [str(h).strip() for h in vals[0]]
        lhdr = [h.lower() for h in hdr]
        sku_c = next((i for i, h in enumerate(lhdr) if h in ("sku name", "sku")), 1)
        # reuse our auto column if present, else first free header slot
        if "fba shipments (auto)" in lhdr:
            col = lhdr.index("fba shipments (auto)")
        else:
            col = max((i for i, h in enumerate(hdr) if h), default=0) + 1
            if ws.col_count < col + 1:
                ws.add_cols(col + 1 - ws.col_count)
            ws.update_cell(1, col + 1, "FBA Shipments (auto)")
        L = col_letter(col)
        updates = []
        for ridx, row in enumerate(vals[2:], start=3):
            sku = row[sku_c].strip() if len(row) > sku_c else ""
            if not sku:
                continue
            txt = text_by_sku.get(sku, "")
            old = row[col].strip() if len(row) > col else ""
            if txt or old:   # write new value, or clear a stale one
                updates.append({"range": f"{L}{ridx}", "values": [[txt]]})
                annotated += 1 if txt else 0
        if updates:
            ws.batch_update(updates, value_input_option="RAW")
    return annotated
