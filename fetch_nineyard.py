"""Pull real 'on the way to FBA' units per SKU from NineYard / Shipyard.

NineYard is the tool used to create the FBA shipments, so it knows the true
quantity of units that have left Sky's warehouse but aren't received at FBA yet —
including shipments in WORKING status that Amazon/Sellerboard don't count until a
delivery appointment exists. This closes the inbound blind spot.

API POLITENESS (NineYard asked us to pull less): every function here is cached.
  • get_inbound_shipments(): results cached to disk (default 4h TTL) — repeat calls
    within the window make ZERO API calls. On a live pull, per-shipment details are
    only re-fetched when that shipment's header changed (status/received/boxes), so
    a typical refresh is ~4 calls instead of ~30. A short delay spaces out calls.
  • get_shipment_skus(): contents of past shipments never change → cached forever.
  • get_sku_images(): full-catalog refresh at most every 45 days.

Credentials live in CACHE_DIR/nineyard_credentials.json (gitignored), same place
as the Google credentials:
    { "email": "...", "password": "...", "companyId": 12473 }
"""
import json
import os
import time

import requests

import config

BASE = "https://backyard.nineyard.com"
CACHE_DIR = os.path.expanduser(config.CACHE_DIR)
CREDS_PATH = os.path.join(CACHE_DIR, "nineyard_credentials.json")
IMAGES_CACHE_PATH = os.path.join(CACHE_DIR, "nineyard_images.json")  # {sku: image_url} cache
INBOUND_CACHE_PATH = os.path.join(CACHE_DIR, "nineyard_inbound_cache.json")
CONTENTS_CACHE_PATH = os.path.join(CACHE_DIR, "nineyard_shipment_contents.json")

# Seconds to wait between consecutive API calls. NineYard's limit is 60 requests per
# minute (shared window) — 1.1s spacing keeps even a worst-case burst safely under it.
_CALL_GAP = 1.1


def _nap():
    time.sleep(_CALL_GAP)


def _get(session, url, **kw):
    """Polite GET: spaced out, and honors HTTP 429 by waiting the Retry-After
    interval (with backoff) before retrying — exactly as NineYard asked."""
    r = None
    for attempt in range(4):
        _nap()
        r = session.get(url, **kw)
        if r.status_code != 429:
            return r
        try:
            wait = float(r.headers.get("Retry-After", "30"))
        except (TypeError, ValueError):
            wait = 30.0
        time.sleep(min(wait, 120) + 5 * attempt)
    return r


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, obj):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f)
    except Exception:
        pass

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
    r = _get(session, f"{BASE}/api/Account/GetAccounts", headers=headers, timeout=30)
    try:
        return {a["name"] for a in r.json() if str(a.get("type", "")).lower() == "amazon"}
    except Exception:
        return set()


def _header_fp(sh):
    """Fingerprint of a shipment header — if this hasn't changed, its per-SKU detail
    can't have changed either, so we skip the GetShippingDetails call entirely."""
    return "|".join(str(sh.get(k, "")) for k in
                    ("status", "receivedQty", "totalQty", "boxCount", "isCompleted", "totalSkus"))


def cache_age_hours():
    """Age of the inbound cache in hours (None if there is no cache yet)."""
    from datetime import datetime, timezone
    obj = _load_json(INBOUND_CACHE_PATH, None)
    if not obj or not obj.get("fetchedAt"):
        return None
    try:
        ts = datetime.fromisoformat(obj["fetchedAt"])
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    except Exception:
        return None


def get_inbound_shipments(statuses=COMMITTED_STATUSES, max_age_hours=4, force=False):
    """Return a list of per-SKU inbound lines, one per (shipment, SKU):
        {sku, qty, amazon_shipment_id, shipment_name, status, type, account}
    where qty = units not yet received. Empty list if NineYard isn't configured.
    Raises RuntimeError on a real failure (bad credentials, network).

    API-friendly: if the disk cache is younger than max_age_hours (and not force),
    it's returned with no API calls at all. On a live pull, shipment details are
    only re-fetched for shipments whose header changed since last time.
    """
    if not is_configured():
        return []

    statuses = set(statuses)
    cache = _load_json(INBOUND_CACHE_PATH, {})

    # Serve from cache when fresh — zero API traffic.
    age = cache_age_hours()
    if (not force and age is not None and age < max_age_hours
            and set(cache.get("statuses", [])) == statuses and "rows" in cache):
        return cache["rows"]

    creds = _load_creds()
    old_details = cache.get("details", {}) if isinstance(cache.get("details"), dict) else {}
    new_details = {}
    rows = []
    with requests.Session() as s:
        token = _auth(s, creds)
        _nap()
        H = {"Authorization": f"Bearer {token}"}
        amazon_accounts = _amazon_account_names(s, H)

        # Pull just the open shipments via the server-side status filter.
        ships = []
        start, page = 0, 200
        while True:
            r = _get(s, f"{BASE}/api/Shipping", headers=H,
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
            hid = str(sh.get("shipmentHeaderId") or "")
            fp = _header_fp(sh)
            cached = old_details.get(hid)
            if cached and cached.get("fp") == fp:
                sku_lines = cached.get("skus", [])          # unchanged → no API call
            else:
                d = _get(s, f"{BASE}/api/Shipping/GetShippingDetails", headers=H,
                          params={"ShipmentHeaderID": sh["shipmentHeaderId"]}, timeout=60).json()
                sku_lines = []
                for sk in (d.get("skus") or []):
                    remaining = (sk.get("qty") or 0) - (sk.get("receivedQty") or 0)
                    if remaining > 0 and sk.get("sku"):
                        sku_lines.append({"sku": sk["sku"], "qty": int(remaining)})
            new_details[hid] = {"fp": fp, "skus": sku_lines}
            for line in sku_lines:
                rows.append({
                    "sku": line["sku"],
                    "qty": line["qty"],
                    "amazon_shipment_id": sh.get("amazonShipmentId") or "",
                    "shipment_header_id": sh.get("shipmentHeaderId") or "",
                    "shipment_name": sh.get("shipmentName") or "",
                    "status": sh.get("status") or "",
                    "type": sh.get("shipmentType") or "",
                    "account": sh.get("account") or "",
                })

    from datetime import datetime, timezone
    _save_json(INBOUND_CACHE_PATH, {
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "statuses": sorted(statuses),
        "rows": rows,
        "details": new_details,
    })
    return rows


def get_inbound_by_sku(statuses=COMMITTED_STATUSES, max_age_hours=4, force=False):
    """Return {sku: units_on_the_way_not_yet_received}, summed across shipments."""
    out = {}
    for r in get_inbound_shipments(statuses, max_age_hours=max_age_hours, force=force):
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

    # Past shipments' contents never change → serve from the permanent cache and
    # only hit the API for FBA ids we've never resolved before.
    contents = _load_json(CONTENTS_CACHE_PATH, {})
    missing = set()
    for f in wanted:
        if f in contents and contents[f]:
            out[f] = contents[f]
        else:
            missing.add(f)
    if not missing:
        return out

    creds = _load_creds()
    with requests.Session() as s:
        token = _auth(s, creds)
        H = {"Authorization": f"Bearer {token}"}

        # Page through shipments to find the headers for the missing FBA ids.
        header_by_fba = {}
        start, page = 0, 200
        while True:
            r = _get(s, f"{BASE}/api/Shipping", headers=H,
                      params={"Statuses": list(ALL_STATUSES), "StartRow": start, "EndRow": start + page},
                      timeout=90)
            batch = r.json()
            if not isinstance(batch, list) or not batch:
                break
            for sh in batch:
                fba = str(sh.get("amazonShipmentId") or "").strip()
                if fba in missing and fba not in header_by_fba:
                    header_by_fba[fba] = sh.get("shipmentHeaderId")
            if len(batch) < page or len(header_by_fba) >= len(missing):
                break
            start += page

        for fba, hid in header_by_fba.items():
            if not hid:
                continue
            d = _get(s, f"{BASE}/api/Shipping/GetShippingDetails", headers=H,
                      params={"ShipmentHeaderID": hid}, timeout=60).json()
            lines = []
            for sk in (d.get("skus") or []):
                sku = sk.get("sku")
                qty = int(sk.get("qty") or 0)
                if sku and qty:
                    lines.append({"sku": sku, "qty": qty})
            out[fba] = lines
            if lines:
                contents[fba] = lines
    _save_json(CONTENTS_CACHE_PATH, contents)
    return out


def get_sku_images(needed_skus=None, max_age_days=45):
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
                    batch = _get(s, f"{BASE}/api/Skus", headers=H, params=params, timeout=60).json()
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
