"""Read Avi's Sky Inventory Ledger — an append-only Google Sheet + Apps Script web app
tracking Sky's China warehouse at the SKU level (read-only shared-token API).

Join key: balances[].fba is the Amazon seller SKU (match trim + case-insensitive).
  balances[].prod  = In Production (ordered, deposit paid, still being made)
  balances[].stock = In Stock (finished sets physically at Sky's warehouse, ready to ship)
  balances[].flag  = data-quality flag (non-empty = needs review)
  events[]         = date, sku (Amazon SKU), type, qty, ready, ref, by, notes
Quantities are in "sets" — pending confirmation that a set == one Amazon sellable unit.
"""
import json
import os

import requests

import config


def _num(v):
    try:
        return float(str(v if v is not None else 0).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def load_creds():
    """(url, token) for the pipeline — from env vars or CACHE_DIR/sky_ledger.json."""
    url = os.environ.get("SKY_LEDGER_URL")
    tok = os.environ.get("SKY_LEDGER_TOKEN")
    if url and tok:
        return url, tok
    path = os.path.join(os.path.expanduser(config.CACHE_DIR), "sky_ledger.json")
    if os.path.exists(path):
        try:
            d = json.load(open(path))
            return d.get("url"), d.get("token")
        except Exception:
            pass
    return None, None


def parse_ready(text, today):
    """Ready date is free-text 'June.30' / 'Aug.15' (month.day, no year). Lenient parse;
    missing year filled with the current year. Returns a date or None."""
    s = str(text or "").replace(".", " ").strip()
    if not s:
        return None
    try:
        from datetime import datetime
        from dateutil import parser as dparse
        return dparse.parse(s, default=datetime(today.year, 1, 1), fuzzy=True).date()
    except Exception:
        return None


def apply_overrides(sky_inventory, ledger, today):
    """Make Avi's ledger the source of truth for warehouse stock + in-production. Mutates
    sky_inventory in place: overrides china_stock / in_production / ready / overdue from the
    ledger (keeps CBM + size from Sky's master sheet). Adds ledger-only SKUs. Returns count."""
    key_by_lower = {str(k).strip().lower(): k for k in sky_inventory}
    n = 0
    for b in ledger.get("balances", []) or []:
        fba = str(b.get("fba", "")).strip()
        if not fba:
            continue
        stock, prod = _num(b.get("stock")), _num(b.get("prod"))
        ready_txt = str(b.get("ready", "")).strip()
        rd = parse_ready(ready_txt, today)
        overdue_days = (today - rd).days if (rd and rd < today and prod > 0) else 0
        upd = {
            "china_stock": stock, "in_production": prod, "ready": ready_txt,
            "overdue_qty": prod if overdue_days > 0 else 0, "overdue_days": overdue_days,
            "flag": str(b.get("flag", "")).strip(),
        }
        tgt = key_by_lower.get(fba.lower())
        if tgt:
            sky_inventory[tgt].update(upd)          # keep cbm_per_unit + size from master
        else:
            upd.setdefault("cbm_per_unit", 0.0)
            upd.setdefault("size", "Standard")
            sky_inventory[fba] = upd
        n += 1
    return n


def fetch_ledger(base_url, token, timeout=60):
    """GET the ledger. Returns {"master": [...], "balances": [...], "events": [...]}.
    Raises on network error or ok=false so the caller can warn and skip."""
    r = requests.get(base_url, params={"api": 2, "token": token}, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    if not d.get("ok"):
        raise RuntimeError("Sky ledger API returned ok=false")
    data = d.get("data", {}) or {}
    return {
        "master": data.get("master", []) or [],
        "balances": data.get("balances", []) or [],
        "events": data.get("events", []) or [],
    }


def balances_by_fba(balances):
    """{amazon_sku_lower: balance_row} for joining to our SKUs."""
    out = {}
    for b in balances or []:
        k = str(b.get("fba", "")).strip().lower()
        if k:
            out[k] = b
    return out
