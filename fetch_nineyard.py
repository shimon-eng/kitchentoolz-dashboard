"""Pull real 'on the way to FBA' units per SKU from NineYard / Shipyard.

NineYard is the tool used to create the FBA shipments, so it knows the true
quantity of units that have left Sky's warehouse but aren't received at FBA yet —
including shipments in WORKING status that Amazon/Sellerboard don't count until a
delivery appointment exists. This closes the inbound blind spot.

Credentials live in CACHE_DIR/nineyard_credentials.json (gitignored), same place
as the Google credentials:
    { "email": "...", "password": "...", "companyId": 12473 }
"""
import json
import os

import requests

import config

BASE = "https://backyard.nineyard.com"
CACHE_DIR = os.path.expanduser(config.CACHE_DIR)
CREDS_PATH = os.path.join(CACHE_DIR, "nineyard_credentials.json")
IMAGES_CACHE_PATH = os.path.join(CACHE_DIR, "nineyard_images.json")  # {sku: image_url} cache

# Statuses that count as "committed and on the way, not yet received at FBA".
# Excludes DRAFT (not submitted to Amazon), CANCELLED/CLOSED/DELETED (void/done).
COMMITTED_STATUSES = ("WORKING", "SHIPPED", "IN_TRANSIT", "RECEIVING", "DELIVERED")


def _secrets_creds():
    """NineYard creds from Streamlit secrets (used on the cloud app). None if absent."""
    try:
        import streamlit as st
        ny = st.secrets.get("nineyard")
        return dict(ny) if ny else None
    except Exception:
        return None


def is_configured() -> bool:
    return os.path.exists(CREDS_PATH) or _secrets_creds() is not None


def _load_creds():
    if os.path.exists(CREDS_PATH):
        with open(CREDS_PATH) as f:
            return json.load(f)
    creds = _secrets_creds()
    if creds:
        return creds
    raise RuntimeError("NineYard credentials not configured")


def _auth(session, creds):
    r = session.post(f"{BASE}/api/OAuth/UsernameToken", json={
        "email": creds["email"],
        "password": creds["password"],
        "companyId": creds.get("companyId", 0),
    }, timeout=30)
    if r.status_code != 200 or not r.text.strip():
        raise RuntimeError(
            f"NineYard login was rejected (HTTP {r.status_code}). "
            "Check email / password / companyId in nineyard_credentials.json."
        )
    return r.json()["accessToken"]


def _amazon_account_names(session, headers):
    """Names of the Amazon-type accounts (so we ignore Wholesale shipments)."""
    r = session.get(f"{BASE}/api/Account/GetAccounts", headers=headers, timeout=30)
    try:
        return {a["name"] for a in r.json() if str(a.get("type", "")).lower() == "amazon"}
    except Exception:
        return set()


def get_inbound_shipments(statuses=COMMITTED_STATUSES):
    """Return a list of per-SKU inbound lines, one per (shipment, SKU):
        {sku, qty, amazon_shipment_id, shipment_name, status, type, account}
    where qty = units not yet received. Empty list if NineYard isn't configured.
    Raises RuntimeError on a real failure (bad credentials, network).
    """
    if not is_configured():
        return []

    creds = _load_creds()
    statuses = set(statuses)
    rows = []
    with requests.Session() as s:
        token = _auth(s, creds)
        H = {"Authorization": f"Bearer {token}"}
        amazon_accounts = _amazon_account_names(s, H)

        # Pull just the open shipments via the server-side status filter.
        ships = []
        start, page = 0, 200
        while True:
            r = s.get(f"{BASE}/api/Shipping", headers=H,
                      params={"Statuses": list(statuses), "StartRow": start, "EndRow": start + page},
                      timeout=90)
            batch = r.json()
            ships += batch
            if len(batch) < page:
                break
            start += page

        def included(sh):
            if sh.get("isCompleted"):
                return False
            if sh.get("status") not in statuses:
                return False
            if amazon_accounts and sh.get("account") not in amazon_accounts:
                return False
            return True

        for sh in ships:
            if not included(sh):
                continue
            d = s.get(f"{BASE}/api/Shipping/GetShippingDetails", headers=H,
                      params={"ShipmentHeaderID": sh["shipmentHeaderId"]}, timeout=60).json()
            for sk in (d.get("skus") or []):
                remaining = (sk.get("qty") or 0) - (sk.get("receivedQty") or 0)
                sku = sk.get("sku")
                if remaining > 0 and sku:
                    rows.append({
                        "sku": sku,
                        "qty": int(remaining),
                        "amazon_shipment_id": sh.get("amazonShipmentId") or "",
                        "shipment_header_id": sh.get("shipmentHeaderId") or "",
                        "shipment_name": sh.get("shipmentName") or "",
                        "status": sh.get("status") or "",
                        "type": sh.get("shipmentType") or "",
                        "account": sh.get("account") or "",
                    })
    return rows


def get_inbound_by_sku(statuses=COMMITTED_STATUSES):
    """Return {sku: units_on_the_way_not_yet_received}, summed across shipments."""
    out = {}
    for r in get_inbound_shipments(statuses):
        out[r["sku"]] = out.get(r["sku"], 0) + r["qty"]
    return out


# All statuses, including finished ones, so we can look up historical (paid,
# already-received) shipments by their Amazon FBA ID for the payment reconciliation.
ALL_STATUSES = COMMITTED_STATUSES + ("DRAFT", "CLOSED", "COMPLETED", "RECEIVED")


def get_shipment_skus(fba_ids):
    """For each Amazon FBA shipment ID, return the SKUs + quantities it contains —
    regardless of status (works for old, already-received shipments). Used by the
    payment reconciliation to prove which products are in each container we paid for.

        get_shipment_skus(["FBA198KQG2Y9"]) -> {"FBA198KQG2Y9": [{"sku":..,"qty":..}, ..]}

    Returns {} if NineYard isn't configured. Unknown FBA IDs map to an empty list.
    """
    if not is_configured():
        return {}
    wanted = {str(f).strip() for f in fba_ids if str(f).strip()}
    out = {f: [] for f in wanted}
    creds = _load_creds()
    with requests.Session() as s:
        token = _auth(s, creds)
        H = {"Authorization": f"Bearer {token}"}

        # Page through ALL shipments to find the headers for the wanted FBA ids.
        header_by_fba = {}
        start, page = 0, 200
        while True:
            r = s.get(f"{BASE}/api/Shipping", headers=H,
                      params={"Statuses": list(ALL_STATUSES), "StartRow": start, "EndRow": start + page},
                      timeout=90)
            batch = r.json()
            if not isinstance(batch, list) or not batch:
                break
            for sh in batch:
                fba = str(sh.get("amazonShipmentId") or "").strip()
                if fba in wanted and fba not in header_by_fba:
                    header_by_fba[fba] = sh.get("shipmentHeaderId")
            if len(batch) < page or len(header_by_fba) >= len(wanted):
                break
            start += page

        for fba, hid in header_by_fba.items():
            if not hid:
                continue
            d = s.get(f"{BASE}/api/Shipping/GetShippingDetails", headers=H,
                      params={"ShipmentHeaderID": hid}, timeout=60).json()
            lines = []
            for sk in (d.get("skus") or []):
                sku = sk.get("sku")
                qty = int(sk.get("qty") or 0)
                if sku and qty:
                    lines.append({"sku": sku, "qty": qty})
            out[fba] = lines
    return out


def get_sku_images(needed_skus=None, max_age_days=14):
    """Return {sku: image_url} (Amazon CDN photos) from NineYard's SKU catalog.

    Cached to IMAGES_CACHE_PATH because the full catalog is large (~50 pages) and
    images rarely change. Refetches only if the cache is missing/old or doesn't
    cover all `needed_skus`. Never raises — returns whatever it has on failure.
    """
    from datetime import datetime, timezone

    cache, fetched_at = {}, None
    if os.path.exists(IMAGES_CACHE_PATH):
        try:
            obj = json.load(open(IMAGES_CACHE_PATH))
            cache, fetched_at = obj.get("images", {}), obj.get("fetchedAt")
        except Exception:
            cache = {}

    fresh = True
    if fetched_at:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)).days
            fresh = age <= max_age_days
        except Exception:
            fresh = True
    have_all = needed_skus is None or all(s in cache for s in needed_skus)
    if cache and fresh and have_all:
        return cache
    if not is_configured():
        return cache

    try:
        creds = _load_creds()
        with requests.Session() as s:
            token = _auth(s, creds)
            H = {"Authorization": f"Bearer {token}"}
            accounts = _amazon_account_names(s, H) or [None]
            images = dict(cache)
            for acct in accounts:
                page = 1
                while True:
                    params = {"PageNumber": page}
                    if acct:
                        params["Account"] = acct
                    batch = s.get(f"{BASE}/api/Skus", headers=H, params=params, timeout=60).json()
                    if not isinstance(batch, list) or not batch:
                        break
                    for it in batch:
                        sku, img = it.get("sku"), it.get("image")
                        if sku and img:
                            images[sku] = img
                    if len(batch) < 100:
                        break
                    page += 1
        json.dump({"fetchedAt": datetime.now(timezone.utc).isoformat(), "images": images},
                  open(IMAGES_CACHE_PATH, "w"))
        return images
    except Exception:
        return cache


if __name__ == "__main__":
    inv = get_inbound_by_sku()
    print(f"{len(inv)} SKUs on the way, {sum(inv.values()):,} units total")
    for sku, q in sorted(inv.items(), key=lambda x: -x[1])[:15]:
        print(f"  {sku:28} {q:>6,}")
