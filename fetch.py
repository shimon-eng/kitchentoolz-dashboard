"""Fetch Sellerboard inventory and China inventory sheets via Google Sheets API."""
import csv
import io
import json
import os
import urllib.request
import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import config

# Read + write: we read Matan's and Shimon's sheets, and write/create the
# partner-facing reorder dashboard sheet. (Broader than before — changing the
# scope list invalidates any cached token, forcing a one-time re-consent.)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CACHE_DIR = os.path.expanduser(config.CACHE_DIR)
CREDS_PATH = os.path.join(CACHE_DIR, "credentials.json")     # OAuth client secrets (from Google Cloud Console)
TOKEN_PATH = os.path.join(CACHE_DIR, "token.json")            # Cached user token (created on first run)
DASHBOARD_STATE_PATH = os.path.join(CACHE_DIR, "dashboard_sheet.json")  # remembers the dashboard sheet we created

# Shimon's own Sellerboard report feeds (Settings → Automation → "Link").
# Each is a secret URL containing an access token — treat it like a password.
# Stored OUTSIDE the repo (alongside token.json) so it never gets committed.
SELLERBOARD_FEEDS_PATH = os.path.join(CACHE_DIR, "sellerboard_feeds.json")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def get_client():
    """Return an authenticated gspread client. On first run, opens a browser for consent."""
    _ensure_cache_dir()

    if not os.path.exists(CREDS_PATH):
        raise FileNotFoundError(
            f"Missing OAuth client secrets. Place credentials.json at:\n  {CREDS_PATH}\n\n"
            "Get one by:\n"
            "  1. Go to https://console.cloud.google.com\n"
            "  2. Create (or pick) a project\n"
            "  3. APIs & Services → Enable: Google Sheets API + Google Drive API\n"
            "  4. APIs & Services → Credentials → Create OAuth Client ID → Desktop app\n"
            "  5. Download the JSON, rename to credentials.json, move to the path above."
        )

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds)


def fetch_sellerboard():
    """Pull all rows from the Sellerboard Inv_Data tab. Returns list[dict]."""
    client = get_client()
    sheet = client.open_by_key(config.SELLERBOARD_SHEET_ID)
    ws = sheet.worksheet(config.SELLERBOARD_TAB)
    # get_all_records uses the first row as headers
    return ws.get_all_records()


def _load_feed_urls():
    """Read the saved Sellerboard feed URLs. Creates a template on first use."""
    if not os.path.exists(SELLERBOARD_FEEDS_PATH):
        _ensure_cache_dir()
        template = {
            "_README": (
                "Paste your Sellerboard feed URLs below. Get them in Sellerboard: "
                "Settings -> Automation -> click 'Link' for each report and copy the URL. "
                "These URLs are secret (they contain your access token) - do not share them."
            ),
            "stock": "",
            "dashboard_by_product": "",
            "dashboard_by_day": "",
        }
        with open(SELLERBOARD_FEEDS_PATH, "w") as f:
            json.dump(template, f, indent=2)
        raise FileNotFoundError(
            "No Sellerboard feed URLs set yet. I just created a file for you to fill in:\n"
            f"  {SELLERBOARD_FEEDS_PATH}\n\n"
            "Open it and paste the 'Link' URLs from Sellerboard "
            "(Settings -> Automation), then run again."
        )
    return json.load(open(SELLERBOARD_FEEDS_PATH))


def fetch_sellerboard_feed(report="stock"):
    """Pull Sellerboard data directly from Shimon's own CSV report feed.

    Drop-in alternative to fetch_sellerboard(): returns list[dict] keyed by the
    same column headers (the Stock report has identical columns to Matan's
    Inv_Data sheet, e.g. 'Estimated Sales Velocity', 'FBA/FBM Stock',
    'Days  of stock  left'), so the merge logic in alerts.py works unchanged.
    """
    urls = _load_feed_urls()
    url = (urls.get(report) or "").strip()
    if not url:
        raise ValueError(
            f"No URL set for the '{report}' feed in:\n  {SELLERBOARD_FEEDS_PATH}\n"
            "Paste the matching 'Link' URL from Sellerboard (Settings -> Automation)."
        )
    with urllib.request.urlopen(url) as resp:
        text = resp.read().decode("utf-8-sig")   # utf-8-sig strips any BOM
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def fetch_china_inventory():
    """Pull all rows from the China inventory sheet. Returns list[dict]."""
    client = get_client()
    sheet = client.open_by_key(config.CHINA_SHEET_ID)
    if isinstance(config.CHINA_TAB, int):
        ws = sheet.get_worksheet(config.CHINA_TAB)
    else:
        ws = sheet.worksheet(config.CHINA_TAB)
    return ws.get_all_records()


def get_discontinued_skus():
    """SKUs the user has marked discontinued (a 'Discontinued' tab in the dashboard
    workbook). These are excluded from all dashboards. Returns a set; empty if no tab."""
    try:
        ws = get_client().open_by_key(config.CHINA_SHEET_ID).worksheet("Discontinued")
        return {str(r.get("SKU", "")).strip() for r in ws.get_all_records() if str(r.get("SKU", "")).strip()}
    except Exception:
        return set()


def get_or_create_dashboard_sheet(client, title="Kitchentoolz Reorder Dashboard"):
    """Return the Spreadsheet we use for the partner-facing dashboard, creating it
    on first use. The sheet ID is remembered in CACHE_DIR so we reuse the same
    sheet (and the same shared link) every run."""
    _ensure_cache_dir()
    # Reuse the remembered sheet if it still exists
    if os.path.exists(DASHBOARD_STATE_PATH):
        try:
            state = json.load(open(DASHBOARD_STATE_PATH))
            return client.open_by_key(state["sheet_id"])
        except Exception:
            pass  # remembered sheet was deleted/inaccessible → recreate below

    sh = client.create(title)
    json.dump({"sheet_id": sh.id, "url": sh.url}, open(DASHBOARD_STATE_PATH, "w"))
    return sh


def share_dashboard(client, email, role="reader", notify=True, message=None):
    """Share the dashboard sheet with one email address (view-only by default)."""
    sh = get_or_create_dashboard_sheet(client)
    sh.share(email, perm_type="user", role=role, notify=notify,
             email_message=message or "Here's the live Kitchentoolz reorder dashboard.")
    return sh.url


if __name__ == "__main__":
    # Quick smoke test: print counts
    print("Fetching Sellerboard…")
    inv = fetch_sellerboard()
    print(f"  → {len(inv)} rows")
    print("Fetching China inventory…")
    china = fetch_china_inventory()
    print(f"  → {len(china)} rows")
    if inv:
        print(f"\nFirst Sellerboard row keys: {list(inv[0].keys())[:6]}…")
    if china:
        print(f"First China row keys: {list(china[0].keys())[:6]}…")
