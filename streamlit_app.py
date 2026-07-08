"""Kitchentoolz reorder dashboard — a polished web app built with Streamlit.

Reads the live 'App Data' tab from the dashboard workbook. Run locally with:
    streamlit run streamlit_app.py
"""
import html
import urllib.parse
from datetime import date

import gspread
import pandas as pd
import streamlit as st

import ai
import config


def _gclient():
    """Return an authenticated gspread client. In the cloud, use the Google service
    account stored in Streamlit secrets; locally, fall back to the OAuth token."""
    try:
        sa = dict(st.secrets["gcp_service_account"])
    except Exception:
        sa = None
    if sa:
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            sa, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds)
    from fetch import get_client   # local development fallback
    return get_client()

st.set_page_config(page_title="KitchenToolz Reorder", page_icon="📦", layout="wide",
                   initial_sidebar_state="collapsed")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&display=swap');

:root {
  --espresso:#2e1c16; --walnut:#5d4037; --coffee:#6f4e37; --caramel:#b07a4f; --latte:#c9a17a;
  --cream:#f7f1e8; --card:#ffffff; --ink:#2b211c; --muted:#9a8c80; --line:#ece3d8;
  --now:#c0392b; --soon:#d98e04; --ok:#2f8f4e; --info:#2e86de;
  --shadow:0 4px 18px rgba(70,45,30,.07); --shadow-lg:0 16px 40px rgba(70,45,30,.16);
}
html, body, [class*="css"], .stMarkdown, input, button, textarea { font-family:'Inter',sans-serif; }
.stApp { background:
  radial-gradient(1100px 520px at 88% -8%, rgba(176,122,79,.13), transparent 60%),
  radial-gradient(900px 480px at -8% 6%, rgba(110,78,55,.10), transparent 55%),
  #f7f1e8; color:var(--ink); }
.block-container { padding-top:1.1rem; padding-bottom:2.4rem; max-width:1140px; }
#MainMenu, footer { visibility:hidden; }
/* keep the header/toolbar VISIBLE — they hold the open-sidebar » arrow — but hide
   Streamlit's own action buttons (Deploy, menu) and the rainbow decoration bar */
[data-testid="stHeader"] { background:transparent; }
.stToolbarActions, [data-testid="stMainMenu"], [data-testid="stAppDeployButton"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display:none; }
::-webkit-scrollbar { width:11px; height:11px; }
::-webkit-scrollbar-thumb { background:#d9cbbb; border-radius:99px; border:3px solid #f7f1e8; }

/* —— HERO —— */
.kt-hero { position:relative; overflow:hidden; color:#fff; border-radius:24px;
  padding:30px 34px; margin-bottom:22px;
  background:linear-gradient(120deg,#2e1c16 0%,#5d4037 52%,#8a5d3b 100%);
  box-shadow:0 18px 44px rgba(46,28,22,.34); }
.kt-hero::before { content:""; position:absolute; top:-90px; right:-60px; width:300px; height:300px;
  background:radial-gradient(circle,rgba(201,161,122,.55),transparent 70%); filter:blur(6px); }
.kt-hero::after { content:""; position:absolute; bottom:-120px; left:18%; width:320px; height:320px;
  background:radial-gradient(circle,rgba(176,122,79,.35),transparent 70%); }
.kt-hero > * { position:relative; z-index:1; }
.kt-hero h1 { margin:0; font-family:'Fraunces',Georgia,serif; font-size:2.25rem; font-weight:600;
  letter-spacing:-.01em; line-height:1.05; }
.kt-hero p { margin:9px 0 0; opacity:.92; font-size:1rem; max-width:560px; line-height:1.5; }
.kt-logoplate { display:inline-flex; align-items:center; justify-content:center; background:#fff;
  border-radius:16px; padding:10px 18px; margin-bottom:14px; box-shadow:0 8px 22px rgba(0,0,0,.22); }
.kt-logo { height:44px; display:block; }
.kt-brand { display:inline-block; font-size:.74rem; font-weight:800; letter-spacing:.26em;
  text-transform:uppercase; color:#f0e6da; margin-bottom:10px; }
.kt-chip { display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,.16);
  backdrop-filter:blur(4px); padding:7px 15px; border-radius:999px; font-size:.83rem; margin-top:16px;
  font-weight:600; border:1px solid rgba(255,255,255,.22); }
.kt-livedot { width:9px; height:9px; border-radius:50%; background:#5be584; display:inline-block;
  box-shadow:0 0 0 0 rgba(91,229,132,.7); animation:ktpulse 1.8s infinite; }
@keyframes ktpulse { 0%{box-shadow:0 0 0 0 rgba(91,229,132,.6);} 70%{box-shadow:0 0 0 8px rgba(91,229,132,0);} 100%{box-shadow:0 0 0 0 rgba(91,229,132,0);} }

/* —— KPI cards —— */
.kt-kpi { position:relative; background:var(--card); border:1px solid var(--line); border-radius:18px;
  padding:18px 20px 16px; box-shadow:var(--shadow); transition:.18s;
  border-top:4px solid var(--ac,var(--coffee)); }
.kt-kpi:hover { box-shadow:var(--shadow-lg); transform:translateY(-3px); }
.kt-kpi .n { font-family:'Fraunces',Georgia,serif; font-size:2.3rem; font-weight:700; line-height:1; color:var(--ink); }
.kt-kpi .l { color:var(--muted); font-size:.74rem; margin-top:9px; text-transform:uppercase; letter-spacing:.06em; font-weight:700; }

/* —— product cards —— */
.kt-card { background:var(--card); border:1px solid var(--line); border-radius:18px; padding:16px 20px;
  margin-bottom:14px; box-shadow:var(--shadow); display:flex; gap:18px; align-items:center; transition:.18s; }
.kt-card:hover { box-shadow:var(--shadow-lg); transform:translateY(-2px); }
.kt-card:hover img { transform:scale(1.05); transition:.18s; }
.kt-card img { width:88px; height:88px; object-fit:contain; border-radius:14px; background:#f4efe7;
  padding:6px; border:1px solid var(--line); }
.kt-noimg { width:88px; height:88px; border-radius:14px; background:#f4efe7; border:1px solid var(--line); }
.kt-body { flex:1; min-width:0; }
.kt-title { font-weight:700; font-size:1.06rem; color:var(--ink); line-height:1.28; }
.kt-sub { color:var(--muted); font-size:.82rem; margin-top:4px; }
.kt-chips { margin-top:10px; }
.kt-mc { display:inline-block; background:#f6efe6; color:#7a6a5c; border-radius:9px; padding:4px 10px;
  font-size:.73rem; margin-right:6px; margin-top:5px; font-weight:600; cursor:help; border:1px solid #efe5d8; }
.kt-act { text-align:right; min-width:140px; }
.kt-actnum { font-family:'Fraunces',Georgia,serif; font-size:1.6rem; font-weight:700; letter-spacing:-.01em; }
.kt-by { color:var(--muted); font-size:.78rem; margin-top:3px; }
.kt-pill { display:inline-block; padding:4px 12px; border-radius:999px; font-size:.71rem; font-weight:800;
  letter-spacing:.03em; }
.kt-now { background:#fde4e1; color:var(--now); }
.kt-soon { background:#fcefcf; color:#a06a00; }
.kt-ok { background:#e1f3e7; color:var(--ok); }
.kt-none { background:#eee8e0; color:#998a7c; }
.kt-overdue { display:inline-block; background:#fcefcf; color:#8a6400; border-radius:9px;
  padding:3px 10px; font-size:.72rem; margin-left:8px; font-weight:700; cursor:help; }
.kt-link { color:inherit; text-decoration:none; }
.kt-link:hover { color:var(--caramel); text-decoration:underline; }
.kt-skulink { color:var(--caramel); text-decoration:none; font-weight:700; }
.kt-skulink:hover { text-decoration:underline; }

details.kt-why { margin-top:11px; }
details.kt-why summary { cursor:pointer; color:var(--caramel); font-size:.82rem; font-weight:700; list-style:none; }
details.kt-why summary::before { content:"💡 "; }
details.kt-why div { background:#faf5ee; border:1px solid var(--line); border-radius:12px; padding:12px 14px;
  margin-top:8px; color:#5a4d42; font-size:.83rem; white-space:pre-wrap; line-height:1.55; }

/* —— stock-breakdown mini-bar —— */
.kt-bar { display:flex; height:8px; border-radius:99px; overflow:hidden; margin-top:11px;
  background:#efe7db; max-width:440px; }
.kt-bar span { height:100%; }
.kt-barkey { font-size:.69rem; color:var(--muted); margin-top:6px; }
.kt-barkey i { font-style:normal; }
.kt-dot { display:inline-block; width:9px; height:9px; border-radius:3px; margin:0 4px 0 10px; vertical-align:middle; }

/* —— detail page —— */
.kt-back { color:var(--caramel); font-weight:700; text-decoration:none; font-size:.95rem; }
.kt-back:hover { text-decoration:underline; }
.kt-foot { text-align:center; color:var(--muted); font-size:.8rem; margin:34px 0 8px; }

/* —— Streamlit native widgets, themed —— */
.stButton > button { border-radius:12px; font-weight:700; border:1px solid var(--line);
  background:#fff; color:var(--coffee); transition:.15s; box-shadow:0 1px 3px rgba(70,45,30,.05); }
.stButton > button:hover { border-color:var(--caramel); color:var(--espresso);
  box-shadow:0 6px 16px rgba(176,122,79,.22); transform:translateY(-1px); }
.stTabs [data-baseweb="tab-list"] { gap:6px; background:#efe6db; padding:6px; border-radius:14px;
  border:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight:700; border-radius:10px; color:#8a7866; padding:8px 16px; }
.stTabs [data-baseweb="tab"]:hover { color:var(--espresso); }
.stTabs [aria-selected="true"] { background:linear-gradient(120deg,#5d4037,#8a5d3b);
  color:#fff !important; box-shadow:0 4px 12px rgba(93,64,55,.3); }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display:none; }
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
  border-radius:11px !important; border-color:var(--line) !important; }
[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:14px;
  padding:12px 16px; box-shadow:var(--shadow); }
[data-testid="stMetricValue"] { font-family:'Fraunces',Georgia,serif; color:var(--ink); }
[data-testid="stExpander"] { border:1px solid var(--line); border-radius:14px; background:#fff;
  box-shadow:var(--shadow); margin-bottom:8px; }
[data-testid="stExpander"] summary { font-size:1.05rem; font-weight:700; padding:10px 6px; }
[data-testid="stExpander"] summary:hover { color:var(--espresso); }
[data-testid="stExpander"] summary p { font-size:1.05rem; }
[data-testid="stSidebar"] { background:#fbf6ef; border-right:1px solid var(--line); }
div[data-testid="stAlert"] { border-radius:13px; }

/* —— KPI stat boxes (clickable popovers, scoped to the kpirow container) —— */
.st-key-kpirow [data-testid="stPopover"] { width:100%; }
.st-key-kpirow [data-testid="stPopover"] > div { width:100%; }
.st-key-kpirow [data-testid="stPopover"] button { width:100%; background:#fff; border:1px solid var(--line);
  border-radius:16px; padding:18px 10px; font-weight:800; font-size:1.05rem; color:var(--ink);
  box-shadow:var(--shadow); transition:.15s; justify-content:center; }
.st-key-kpirow [data-testid="stPopover"] button:hover { transform:translateY(-2px); box-shadow:var(--shadow-lg);
  border-color:var(--caramel); color:var(--ink); }
[data-testid="stPopoverBody"] { min-width:min(760px, 92vw); border-radius:16px; }

@media (max-width: 640px) {
  .kt-hero { padding:22px; } .kt-hero h1 { font-size:1.7rem; }
  .kt-card { flex-wrap:wrap; gap:12px; }
  .kt-act { text-align:left; min-width:100%; margin-top:4px; }
  .block-container { padding-left:.6rem; padding-right:.6rem; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

PILL = {"order now": ("kt-now", "ORDER NOW"), "order soon": ("kt-soon", "ORDER SOON"),
        "ok": ("kt-ok", "OK"), "no sales": ("kt-none", "NO SALES")}
EMOJI = {"order now": "🔴", "order soon": "🟡", "ok": "🟢", "no sales": "⚪"}


@st.cache_data(ttl=300, show_spinner="Loading the latest numbers…")
def load_data():
    ws = _gclient().open_by_key(config.CHINA_SHEET_ID).worksheet("App Data")
    return pd.DataFrame(ws.get_all_records())


@st.cache_data
def logo_uri():
    """Return a base64 data-URI for logo.png if present (so it works on the cloud too)."""
    import base64
    import os
    for name, mime in (("logo.png", "png"), ("logo.jpg", "jpeg"), ("logo.jpeg", "jpeg")):
        if os.path.exists(name):
            return f"data:image/{mime};base64," + base64.b64encode(open(name, "rb").read()).decode()
    return None


@st.cache_data(ttl=300)
def load_discontinued():
    try:
        ws = _gclient().open_by_key(config.CHINA_SHEET_ID).worksheet("Discontinued")
        return {str(r.get("SKU", "")).strip() for r in ws.get_all_records() if str(r.get("SKU", "")).strip()}
    except Exception:
        return set()


@st.cache_data(ttl=600, show_spinner=False)
def load_inbound():
    """The 'Inbound Shipments' tab (written by the morning pipeline from 9Yards)."""
    try:
        ws = _gclient().open_by_key(config.CHINA_SHEET_ID).worksheet("Inbound Shipments")
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def load_ppc():
    """The 'PPC Suggestions' tab (written by the morning pipeline from Amazon Ads).
    Empty until the Ads connection is set up and the pipeline has run once."""
    try:
        ws = _gclient().open_by_key(config.CHINA_SHEET_ID).worksheet("PPC Suggestions")
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame()


_STATUS_LABEL = {
    "WORKING": "📝 Working (not shipped yet)", "SHIPPED": "🚚 Shipped",
    "IN_TRANSIT": "🚚 In transit", "RECEIVING": "📥 Receiving at FBA",
    "DELIVERED": "✅ Delivered",
}


def _disc_ws():
    return _gclient().open_by_key(config.CHINA_SHEET_ID).worksheet("Discontinued")


def hide_skus(skus):
    ws = _disc_ws()
    have = load_discontinued()
    for s in skus:
        if s not in have:
            ws.append_row([s, "", str(date.today())], value_input_option="USER_ENTERED")


def restore_skus(skus):
    ws = _disc_ws()
    rows = ws.get_all_values()
    keep = [rows[0]] + [r for r in rows[1:] if r and r[0].strip() not in skus]
    ws.clear()
    ws.update(keep, range_name="A1", value_input_option="USER_ENTERED")


def _int(x):
    try:
        return int(float(str(x).replace(",", "")))
    except (ValueError, TypeError):
        return 0


def freshness(df):
    """Return ('how long ago', is_stale) from the data's 'Updated' timestamp."""
    from datetime import datetime, timezone
    try:
        ts = datetime.fromisoformat(str(df["Updated"].iloc[0]))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        hrs = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    except Exception:
        return "", False
    if hrs < 1:
        ago = "just now"
    elif hrs < 24:
        ago = f"{int(hrs)}h ago"
    else:
        ago = f"{int(hrs // 24)}d ago"
    return ago, hrs > 28


def seller_central_url(sku):
    """Deep-link to this SKU in Amazon Seller Central's Manage Inventory search."""
    return ("https://sellercentral.amazon.com/myinventory/inventory?fulfilledBy=all&page=1&pageSize=100"
            "&searchField=all&searchTerm=" + urllib.parse.quote(str(sku)) +
            "&sort=available_desc&status=all&ref_=xx_invmgr_favb_xx")


def card_html(row, action_html, why_field):
    prio = str(row.get("Priority", ""))
    pill_cls, pill_txt = PILL.get(prio, ("kt-none", prio.upper()))
    img = str(row.get("Image", ""))
    imgtag = f'<img src="{html.escape(img)}">' if img.startswith("http") else '<div class="kt-noimg"></div>'

    asin = html.escape(str(row.get("ASIN", "")))
    sku = html.escape(str(row.get("SKU", "")))
    supplier = html.escape(str(row.get("Supplier", "")))
    product = html.escape(str(row.get("Product", "")))
    amz = f"https://www.amazon.com/dp/{asin}" if asin else ""
    sc = seller_central_url(str(row.get("SKU", "")))
    view_url = "?view=" + urllib.parse.quote(str(row.get("SKU", "")))
    title_html = f'<a href="{view_url}" target="_self" class="kt-link" title="See full details">{product}</a>'
    sub_bits = [
        f'<a href="{sc}" target="_blank" class="kt-skulink" title="Open this SKU in Amazon Seller Central inventory">{sku} ↗</a>',
        f'🏭 {supplier}',
    ]
    if amz:
        sub_bits.append(f'<a href="{amz}" target="_blank" class="kt-skulink" title="Open the Amazon buyer page for this ASIN">🛒 {asin}</a>')
    sub = " &nbsp;·&nbsp; ".join(sub_bits)

    chip_data = [
        (f"Sells {row.get('Sells per day','')}/day", "Average units sold per day (from Amazon / Sellerboard)"),
        (f"FBA {_int(row.get('FBA days left'))}d left", "Days of stock left in Amazon at the current sales pace"),
        (f"China {_int(row.get('China warehouse')):,}", "Units ready in Sky's China warehouse"),
        (f"On the way {_int(row.get('On the way')):,}", "Units already heading to Amazon (live from 9Yards)"),
        (f"Cover {_int(row.get('Days of cover'))}d", "Total days your whole pipeline will last"),
    ]
    chips = "".join(f'<span class="kt-mc" title="{html.escape(t)}">{c}</span>' for c, t in chip_data)
    _size = str(row.get("Size", "")).strip().lower()
    if _size:
        _slabel = "🛒 Oversize" if _size == "oversize" else "📦 Standard"
        chips += f'<span class="kt-mc" title="Size class (from Sky\'s Standard/Oversize tabs)">{_slabel}</span>'
    overdue = (f'<span class="kt-overdue" title="These in-production units are overdue at Sky — chase him">'
               f'⚠️ {_int(row.get("Overdue days"))}d overdue at Sky</span>'
               if _int(row.get("Overdue days")) > 0 else "")
    _basis = str(row.get("Demand basis", "")).strip().lower()
    if _basis in ("past sales", "your estimate"):
        overdue += (f'<span class="kt-overdue" style="background:#e7dcff;color:#5b3a9b" '
                    f'title="Out of stock at Amazon — this is flagged from {_basis}, not current sales">'
                    f'📊 out of stock · from {_basis}</span>')
    why = str(row.get(why_field, "")).strip()
    why_html = (f'<details class="kt-why"><summary>Why this number?</summary>'
                f'<div>{html.escape(why)}</div></details>') if why else ""
    by = (f'<div class="kt-by">by {html.escape(str(row.get("Order by","")))}</div>'
          if str(row.get("Order by", "")).strip() else "")
    seg = [(_int(row.get("In FBA")), "#2e86de", "In FBA"), (_int(row.get("On the way")), "#1f8a70", "On the way"),
           (_int(row.get("China warehouse")), "#e0a800", "China"), (_int(row.get("In production")), "#9b59b6", "In production")]
    _tot = sum(v for v, _, _ in seg) or 1
    bar = "".join(f'<span style="width:{v / _tot * 100:.1f}%;background:{c}" title="{lbl}: {v:,}"></span>'
                  for v, c, lbl in seg if v > 0)
    bar_html = f'<div class="kt-bar">{bar}</div>' if bar else ""
    edge = {"order now": "#c0392b", "order soon": "#d98e04", "ok": "#2f8f4e"}.get(prio, "#e6dccf")
    return (
        f'<div class="kt-card" style="border-left:5px solid {edge}">{imgtag}<div class="kt-body">'
        f'<div><span class="kt-pill {pill_cls}">{pill_txt}</span>{overdue}</div>'
        f'<div class="kt-title">{title_html}</div>'
        f'<div class="kt-sub">{sub}</div>'
        f'<div class="kt-chips">{chips}</div>{bar_html}{why_html}</div>'
        f'<div class="kt-act">{action_html}{by}</div></div>'
    )


def render(rows, action_fn, why_field):
    if not len(rows):
        st.success("Nothing here right now. ✅")
        return
    st.markdown("".join(card_html(r, action_fn(r), why_field) for _, r in rows.iterrows()),
                unsafe_allow_html=True)


def copy_button(text, label="📋  Copy all for 9Yards",
                done_msg="✓ Copied! Paste into 9Yards → Paste Bulk.", height=62):
    """A big, fancy one-click 'copy to clipboard' button (works inside Streamlit's iframe)."""
    import json as _json
    import streamlit.components.v1 as components
    payload = _json.dumps(text)
    done = _json.dumps(done_msg)
    components.html(f"""
      <style>
        .cpybtn {{ background:linear-gradient(120deg,#1f8a70,#0f3d5e); color:#fff; border:none;
          padding:13px 26px; border-radius:13px; font-size:1.02rem; font-weight:800; cursor:pointer;
          box-shadow:0 6px 18px rgba(31,138,112,.35); font-family:Inter,system-ui,sans-serif; }}
        .cpybtn:hover {{ filter:brightness(1.08); transform:translateY(-1px); }}
        .cpymsg {{ margin-left:14px; color:#1f8a70; font-weight:700; font-family:Inter,system-ui,sans-serif; }}
      </style>
      <button class="cpybtn" onclick="cpy()">{label}</button>
      <span class="cpymsg" id="m"></span>
      <script>
        const T = {payload};
        function cpy() {{
          const ta=document.createElement('textarea'); ta.value=T;
          ta.style.position='fixed'; ta.style.opacity='0'; document.body.appendChild(ta); ta.focus(); ta.select();
          let ok=false; try {{ ok=document.execCommand('copy'); }} catch(e) {{}}
          document.body.removeChild(ta);
          document.getElementById('m').innerText = ok ? {done} : 'Copy failed — select the text and press Ctrl+C.';
        }}
      </script>
    """, height=height)


def unit_math_text(r):
    """The pipeline arithmetic for one product, laid out so the columns line up —
    every unit, where it is, added up, then divided by the sales pace into days."""
    fba = _int(r.get("In FBA"))
    otw = _int(r.get("On the way"))
    ch = _int(r.get("China warehouse"))
    prod = _int(r.get("In production"))
    total = fba + otw + ch + prod
    cover = _int(r.get("Days of cover"))
    try:
        vel = float(str(r.get("Sells per day", 0)).replace(",", ""))
    except (ValueError, TypeError):
        vel = 0.0

    def n(x):
        return f"{x:>9,}"

    lines = [
        "WHERE YOUR UNITS ARE",
        f"  In FBA  (at Amazon)        {n(fba)}",
        f"  On the way to Amazon       {n(otw)}",
        f"  China warehouse  (Sky)     {n(ch)}",
        f"  In production    (Sky)     {n(prod)}",
        "  " + "─" * 34,
        f"  Total pipeline             {n(total)}  units",
        "",
        "HOW LONG THAT LASTS",
    ]
    if vel > 0:
        lines.append(f"  {total:,} units  ÷  {vel:g}/day   =   {cover:,} days of cover")
    else:
        lines.append("  No sales right now — days of cover not applicable.")
    return "\n".join(lines)


def render_inbound_table(rows, show_sku=True):
    """One inbound-shipments table with Seller Central + 9Yards links and friendly
    statuses. Shared by the 'Units on the way' stat box and the product breakdown."""
    rows = rows.copy()
    rows["Open in Amazon"] = rows["Shipment ID"].astype(str).apply(
        lambda x: f"https://sellercentral.amazon.com/fba/inbound-shipment/summary/{x}/shipmentEvents"
        if x.strip() else "")
    if "9Yards ID" in rows.columns:
        rows["Open in 9Yards"] = rows["9Yards ID"].astype(str).apply(
            lambda x: f"https://app.nineyard.com/shipyard/shipments/detail/{x}"
            if x.strip() and x.strip().lower() != "nan" else "")
    if "Status" in rows.columns:
        rows["Status"] = rows["Status"].astype(str).apply(
            lambda s: _STATUS_LABEL.get(s.strip().upper(), s))
    units = int(rows["Units on the way"].apply(_int).sum()) if "Units on the way" in rows.columns else 0
    st.caption(f"**{rows['Shipment ID'].nunique()} shipment(s) · {units:,} units.** "
               "Open a shipment in Amazon Seller Central or 9Yards (you must be logged in).")
    cols = ["Shipment ID", "Shipment name", "Status", "Type"] + (["SKU"] if show_sku else []) + \
           ["Units on the way", "Open in Amazon", "Open in 9Yards"]
    st.dataframe(
        rows[[c for c in cols if c in rows.columns]],
        hide_index=True, use_container_width=True,
        column_config={
            "Open in Amazon": st.column_config.LinkColumn("Seller Central", display_text="View ↗"),
            "Open in 9Yards": st.column_config.LinkColumn("9Yards", display_text="View ↗"),
            "Units on the way": st.column_config.NumberColumn(format="%d"),
        })


def show_otw_shipments(r):
    """Break one product's 'On the way' number down into its inbound shipments."""
    otw = _int(r.get("On the way"))
    if otw <= 0:
        return
    inb = load_inbound()
    sku = str(r.get("SKU", "")).strip()
    rows = (inb[inb["SKU"].astype(str).str.strip() == sku]
            if not inb.empty and "SKU" in inb.columns else inb.iloc[0:0])
    st.markdown(f"#### 🚚 The {otw:,} on the way — which shipments")
    if rows.empty or "Shipment ID" not in rows.columns:
        st.caption("Per-shipment detail will appear after the next morning update.")
        return
    render_inbound_table(rows, show_sku=False)


def product_card(r):
    """The full single-product breakdown: photo, headline action, the numbers,
    the math spelled out, and the plain-English 'why'. Shared by the detail page
    (click a product) and the 🔎 Look up tab (type an ASIN or SKU)."""
    st.markdown(f"## {r['Product']}")
    c1, c2 = st.columns([1, 2], vertical_alignment="top")
    with c1:
        if str(r.get("Image", "")).startswith("http"):
            st.image(r["Image"], use_container_width=True)
    with c2:
        emoji = EMOJI.get(str(r.get("Priority", "")), "")
        st.markdown(f"### {emoji} {r.get('What to do', '')}")
        asin = str(r.get("ASIN", "")).strip()
        line = f"[{r['SKU']}]({seller_central_url(r['SKU'])}) · 🏭 {r['Supplier']}"
        if asin:
            line += f" · [🛒 View on Amazon](https://www.amazon.com/dp/{asin})"
        st.markdown(line)
        g = lambda k: f"{_int(r.get(k)):,}"
        a, b, c = st.columns(3)
        a.metric("Sells / day", r.get("Sells per day", ""))
        b.metric("FBA days left", _int(r.get("FBA days left")))
        c.metric("Days of cover", _int(r.get("Days of cover")))
        d, e, f = st.columns(3)
        d.metric("In FBA", g("In FBA"))
        e.metric("On the way", g("On the way"))
        f.metric("China warehouse", g("China warehouse"))
        h, i, j = st.columns(3)
        h.metric("In production", g("In production"))
        i.metric("Ship qty", g("Ship qty"))
        j.metric("Order qty", g("Order qty"))
    st.markdown("#### 🧮 The math — every unit, spelled out")
    st.code(unit_math_text(r), language=None)
    show_otw_shipments(r)
    ws, wo = str(r.get("Why ship", "")).strip(), str(r.get("Why order", "")).strip()
    if ws:
        st.markdown("#### 🚢 Why this ship quantity")
        st.info(ws)
    if wo:
        st.markdown("#### 🏭 Why this order quantity")
        st.info(wo)
    if _int(r.get("Overdue days")) > 0:
        st.warning(f"⚠️ {_int(r.get('Overdue days'))} days overdue at the supplier — chase them.")


def show_detail(df, sku):
    """A full detail 'page' for one product (opened by clicking a product name)."""
    st.markdown('<a class="kt-back" href="?" target="_self">← Back to dashboard</a>', unsafe_allow_html=True)
    m = df[df["SKU"].astype(str) == str(sku)]
    if m.empty:
        st.warning(f"Product '{sku}' isn't on the dashboard right now.")
        return
    product_card(m.iloc[0])
    st.markdown('<a class="kt-back" href="?" target="_self">← Back to dashboard</a>', unsafe_allow_html=True)


# Shared look + clipboard JS for the 📣 Ads HTML tables (inline 📋 copy icons).
_ADS_CSS = """
    <style>
      * { box-sizing:border-box; }
      body { margin:0; font-family:Inter,system-ui,sans-serif; color:#2b211c; }
      .wrap { max-height:560px; overflow:auto; border:1px solid #ece3d8; border-radius:12px; }
      table { border-collapse:collapse; width:100%; font-size:13px; }
      thead th { position:sticky; top:0; background:#2e5984; color:#fff; font-weight:700;
        text-align:left; padding:9px 10px; font-size:11px; z-index:1; }
      td { padding:8px 10px; border-bottom:1px solid #f0e9df; vertical-align:middle; }
      tr:hover td { background:#faf5ee; }
      td img { width:40px; height:40px; object-fit:contain; border-radius:8px; background:#f4efe7;
        border:1px solid #ece3d8; }
      .noimg { width:40px; height:40px; border-radius:8px; background:#f4efe7; border:1px solid #ece3d8; }
      .prod { font-weight:600; max-width:230px; }
      .camp { color:#5d4037; max-width:300px; }
      .camplist { color:#7a6a5c; font-size:11px; line-height:1.4; max-width:340px;
        max-height:80px; overflow:auto; display:block; }
      .mono { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px; white-space:nowrap; }
      .ctr { text-align:center; white-space:nowrap; }
      .hero { color:#c8a415; }
      .pct { color:#9a8c80; }
      .cp { cursor:pointer; margin-left:5px; opacity:.55; font-size:12px; user-select:none; }
      .cp:hover { opacity:1; }
      a { color:#b07a4f; text-decoration:none; font-weight:700; }
      a:hover { text-decoration:underline; }
    </style>"""
_ADS_JS = """
    <script>
      function cp(el) {
        const t = el.getAttribute('data-v');
        const ta = document.createElement('textarea'); ta.value = t;
        ta.style.position='fixed'; ta.style.opacity='0';
        document.body.appendChild(ta); ta.focus(); ta.select();
        try { document.execCommand('copy'); } catch(e) {}
        document.body.removeChild(ta);
        const o = el.textContent; el.textContent = '✓';
        setTimeout(function(){ el.textContent = o; }, 900);
      }
    </script>"""


def _cp_icon(v):
    """A small clickable 📋 copy icon carrying its value (one click → clipboard)."""
    import html as _html
    return (f'<span class="cp" data-v="{_html.escape(str(v), quote=True)}" '
            f'onclick="cp(this)" title="Copy">📋</span>')


def _render_ads_table(thead, rows_html, n):
    import streamlit.components.v1 as components
    doc = (_ADS_CSS + f'<div class="wrap"><table>{thead}<tbody>{rows_html}</tbody></table></div>'
           + _ADS_JS)
    components.html(doc, height=min(610, 96 + n * 49), scrolling=False)


def _img_cell(r):
    import html as _html
    img = str(r.get("Image", "")).strip()
    return (f'<img src="{_html.escape(img, quote=True)}">' if img.startswith("http")
            else '<div class="noimg"></div>')


def _amz_link(r):
    asin = str(r.get("ASIN", "")).strip()
    return f'<a href="https://www.amazon.com/dp/{asin}" target="_blank">Amazon ↗</a>' if asin else ""


def ads_budget_table(budgets):
    """Budget-taper suggestions — compact table with an inline 📋 next to each SKU and
    campaign name (one click copies it; no Ctrl+C popup)."""
    import html as _html
    rows = ""
    for _, r in budgets.iterrows():
        product = _html.escape(str(r.get("Product", ""))[:48])
        sku = str(r.get("SKU", ""))
        camp = str(r.get("Campaign", ""))
        days = int(float(r.get("Days left", 0) or 0))
        cur = float(r.get("Current budget", 0) or 0)
        sug = float(r.get("Suggested budget", 0) or 0)
        pct = _html.escape(str(r.get("Change", "")))
        hero = "★" if str(r.get("Hero", "")).strip() else ""
        rows += (
            f'<tr><td>{_img_cell(r)}</td>'
            f'<td class="prod">{product}</td>'
            f'<td class="mono">{_html.escape(sku)} {_cp_icon(sku)}</td>'
            f'<td class="ctr hero">{hero}</td>'
            f'<td class="ctr">{days}d</td>'
            f'<td class="ctr">${cur:.2f} → <b>${sug:.2f}</b> <span class="pct">{pct}</span></td>'
            f'<td class="camp">{_html.escape(camp[:54])} {_cp_icon(camp)}</td>'
            f'<td class="ctr">{_amz_link(r)}</td></tr>'
        )
    thead = ('<thead><tr><th></th><th>Product</th><th>SKU</th><th>★</th><th>Days</th>'
             '<th>Budget</th><th>Campaign &nbsp;(📋 to copy)</th><th>Amazon</th></tr></thead>')
    _render_ads_table(thead, rows, len(budgets))


def ads_pause_table(pauses):
    """One row per low/out-of-stock SKU still advertised in the Catch All portfolio.
    Shows how many Catch All campaigns/ad groups it's in + the campaign list. Copy the
    SKU and filter the Catch All portfolio by it to pause all its ads at once."""
    import html as _html
    rows = ""
    for _, r in pauses.iterrows():
        product = _html.escape(str(r.get("Product", ""))[:46])
        sku = str(r.get("SKU", ""))
        camplist = str(r.get("Campaign", ""))
        spread = _html.escape(str(r.get("Detail", "")))
        days = int(float(r.get("Days left", 0) or 0))
        hero = "★" if str(r.get("Hero", "")).strip() else ""
        dlabel = '<b style="color:#c0392b">OUT</b>' if days <= 0 else f"{days}d"
        rows += (
            f'<tr><td>{_img_cell(r)}</td>'
            f'<td class="prod">{product}</td>'
            f'<td class="mono">{_html.escape(sku)} {_cp_icon(sku)}</td>'
            f'<td class="ctr hero">{hero}</td>'
            f'<td class="ctr">{dlabel}</td>'
            f'<td class="ctr">{spread}</td>'
            f'<td class="camplist">{_html.escape(camplist)}</td>'
            f'<td class="ctr">{_amz_link(r)}</td></tr>'
        )
    thead = ('<thead><tr><th></th><th>Product</th><th>SKU</th><th>★</th><th>Days</th>'
             '<th>Spread</th><th>Catch All campaigns it\'s in</th><th>Amazon</th></tr></thead>')
    _render_ads_table(thead, rows, len(pauses))


def show_ads(ppc):
    """📣 Ads tab: inventory-aware PPC suggestions. SUGGESTION-ONLY — a report of what
    the tool would do; it never touches your campaigns. You decide and act in Amazon."""
    st.info("💡 **Suggestion-only.** These are ideas based on your stock levels — nothing here "
            "changes your Amazon ads. Review them and make any change yourself in Seller Central / Ads.")

    if ppc is None or ppc.empty:
        st.caption("No PPC suggestions yet. They appear here after the next morning update "
                   "(and once the Amazon Ads connection has been set up).")
        return

    budgets = ppc[ppc["Type"].astype(str) == "Budget ↓"].copy()
    pauses = ppc[ppc["Type"].astype(str) == "Remove low SKU"].copy()

    st.markdown(f"### 🔻 Budget tapers &nbsp;·&nbsp; {len(budgets)}")
    st.caption("Single-product campaigns whose product is getting low on FBA stock — ease the daily "
               "budget down so you don't sell out faster than you can restock. (Glides back up on its "
               "own as stock recovers. Catch All campaigns are never touched here.)")
    if budgets.empty:
        st.success("No budget changes suggested right now. ✅")
    else:
        ads_budget_table(budgets)

    st.divider()
    st.markdown(f"### ⏸️ Remove low SKUs from Catch All &nbsp;·&nbsp; {len(pauses)} products")
    st.caption("Low / out-of-stock products still advertised inside your **Catch All** portfolio. "
               "Each row is one product and how widely it's still running there. **Fastest fix:** copy "
               "the SKU (📋), open the Catch All portfolio, search that SKU, and pause all its ads at "
               "once — other products in those campaigns stay untouched. Re-add it yourself once "
               "restocked. (The tool never re-enables ads on its own.)")
    if pauses.empty:
        st.success("No low-stock SKUs over-advertised in Catch All right now. ✅")
    else:
        ads_pause_table(pauses)


GUIDE_MD = (
    "**The four boxes** up top are today's headlines — click one to see the "
    "products or shipments behind the number.\n\n"
    "**🚢 Ship to FBA** — what to send from the China warehouse to Amazon now. "
    "Adjust quantities, copy the list for 9Yards, or send it to Sky's sheet.\n\n"
    "**🏭 Reorder** — what to manufacture next, how many, and by when.\n\n"
    "**📋 All products** — search anything by name, SKU, or ASIN. "
    "Click a product name for its full breakdown.\n\n"
    "**📣 Ads** — suggestions to ease ad spend on low-stock products. "
    "Suggestion-only; nothing changes automatically.\n\n"
    "**🤖 Ask AI** — ask questions about your inventory in plain English.\n\n"
    "⚙️ To hide a discontinued product, open the sidebar (**»** arrow, top-left) → Manage products.\n\n"
    "_Data refreshes every morning at 6am automatically._")

# ---- top bar: guide + refresh ----------------------------------------------
top_l, top_g, top_r = st.columns([4, 1.1, 1])
with top_g:
    with st.popover("❓ Quick guide", use_container_width=True):
        st.markdown(GUIDE_MD)
with top_r:
    if st.button("🔄 Refresh", use_container_width=True):
        load_data.clear()
        st.rerun()

df = load_data()
disc = load_discontinued()
if disc:
    df = df[~df["SKU"].astype(str).str.strip().isin(disc)].copy()

# ---- product detail page (when a product name is clicked) -----------------
_view = st.query_params.get("view")
if _view:
    show_detail(df, _view)
    st.stop()

# ---- sidebar: quick guide + manage products --------------------------------
with st.sidebar:
    st.header("🧭 Quick guide")
    st.markdown(GUIDE_MD)
    st.divider()
    st.header("⚙️ Manage products")
    st.caption("Hide products you've discontinued so they drop off the dashboard.")
    opts = {f"{str(r['Product'])[:42]} — {r['SKU']}": str(r["SKU"]) for _, r in df.iterrows()}
    to_hide = st.multiselect("Pick products to hide", list(opts.keys()))
    if st.button("🚫 Hide selected", use_container_width=True, disabled=not to_hide):
        hide_skus([opts[k] for k in to_hide])
        load_discontinued.clear()
        st.rerun()
    st.divider()
    hidden = sorted(load_discontinued())
    st.caption(f"Currently hidden: {len(hidden)}")
    if hidden:
        to_restore = st.multiselect("Restore (un-hide)", hidden)
        if st.button("↩️ Restore selected", use_container_width=True, disabled=not to_restore):
            restore_skus(set(to_restore))
            load_discontinued.clear()
            st.rerun()

ship = df[df["Ship qty"].apply(_int) > 0].copy()
ship = ship.assign(_d=ship["FBA days left"].apply(_int)).sort_values("_d")
reorder = df[df["Order qty"].apply(_int) > 0].copy()
reorder = reorder.assign(_p=reorder["Priority"].map({"order now": 0, "order soon": 1}).fillna(2)).sort_values("_p")
n_overdue = int((df["Overdue days"].apply(_int) > 0).sum())
otw_total = int(df["On the way"].apply(_int).sum())

# ---- hero + KPIs ----------------------------------------------------------
ago, stale = freshness(df)
if stale:
    st.markdown(
        '<div style="background:#fff3cd;color:#856404;border-radius:12px;padding:12px 16px;'
        'margin-bottom:14px;font-weight:600;border:1px solid #ffe69c;">⚠️ These numbers may be out of '
        f'date — last refreshed {ago}. Ask Shimon to run the morning update.</div>', unsafe_allow_html=True)
_txt = (f"Updated {ago} · {len(df)} products tracked" if ago else f"Live data · {len(df)} products tracked")
chip = f'<span class="kt-livedot"></span>{_txt}'
_logo = logo_uri()
brand = (f'<div class="kt-logoplate"><img class="kt-logo" src="{_logo}"></div>' if _logo
         else '<div class="kt-brand">🍴 KitchenToolz</div>')
st.markdown(
    f'<div class="kt-hero">{brand}'
    '<h1>China Reorder Command Center</h1>'
    '<p>What to ship, what to order, and why — updated every morning. '
    '<span style="opacity:.75;font-size:.88rem">New here? Open the sidebar (» top-left) for a 1-minute guide.</span></p>'
    f'<span class="kt-chip">{chip}</span></div>',
    unsafe_allow_html=True)

def _mini_table(frame, cols):
    show = frame[[c for c in cols if c in frame.columns]]
    if show.empty:
        st.caption("Nothing here right now. ✅")
    else:
        st.dataframe(show, hide_index=True, use_container_width=True)


# ---- the four headline stat boxes (click to see what's behind each) --------
_kpirow = st.container(key="kpirow")
with _kpirow:
    k1, k2, k3, k4 = st.columns(4)
with k1:
    with st.popover(f"🚢 :green[**{len(ship)}**] to ship now", use_container_width=True):
        st.caption("Running low at Amazon, with stock ready in the China warehouse — "
                   "build the shipment in the **🚢 Ship to FBA** tab.")
        _mini_table(ship, ["Product", "SKU", "Ship qty", "FBA days left", "Size", "Supplier"])
with k2:
    with st.popover(f"🏭 :red[**{len(reorder)}**] to reorder", use_container_width=True):
        st.caption("The pipeline won't cover the next make-and-ship cycle — "
                   "order quantities and reasons are in the **🏭 Reorder** tab.")
        _mini_table(reorder, ["Product", "SKU", "Order qty", "Priority", "Order by", "Supplier"])
with k3:
    with st.popover(f"⚠️ :orange[**{n_overdue}**] overdue at Sky", use_container_width=True):
        st.caption("In-production units past their promised ready date — worth chasing Sky. "
                   "Sorted worst-first.")
        if "Overdue days" in df.columns:
            _od = df[df["Overdue days"].apply(_int) > 0].copy()
            _od["_o"] = _od["Overdue days"].apply(_int)
            _od = _od.sort_values("_o", ascending=False)
        else:
            _od = df.iloc[0:0]
        _mini_table(_od, ["Product", "SKU", "In production", "Overdue days", "Supplier"])
with k4:
    with st.popover(f"📦 :blue[**{otw_total:,}**] on the way", use_container_width=True):
        _inb = load_inbound()
        if not _inb.empty and "SKU" in _inb.columns:
            # only shipments for SKUs that are part of the China reorder dashboard
            _china = set(df["SKU"].astype(str).str.strip())
            _inb = _inb[_inb["SKU"].astype(str).str.strip().isin(_china)]
        if _inb.empty or "Shipment ID" not in _inb.columns:
            st.caption("No shipment detail yet — it appears after the next morning update.")
        else:
            render_inbound_table(_inb)
        st.divider()
        st.caption("Made new shipments today? Pull the latest from 9Yards — this also refreshes "
                   "the **FBA Shipments** traceability column on Sky's sheet.")
        if st.button("🔄 Update now from 9Yards (~1 min)", key="inb_sync"):
            try:
                import fetch_nineyard
                import inbound_sync
                if not fetch_nineyard.is_configured():
                    st.warning("9Yards login isn't set up here. On the cloud site, add a "
                               "`[nineyard]` section (email / password / companyId) in "
                               "Streamlit → Settings → Secrets.")
                else:
                    with st.spinner("Pulling live shipments from 9Yards…"):
                        _rows = fetch_nineyard.get_inbound_shipments()
                    with st.spinner("Updating the dashboard + Sky's sheet…"):
                        _gc = _gclient()
                        inbound_sync.write_inbound_shipments_tab(
                            _gc.open_by_key(config.CHINA_SHEET_ID), _rows)
                        _n = inbound_sync.write_fba_ids_to_sky(_gc, _rows)
                    load_inbound.clear()
                    st.success(f"✅ Updated — {len(_rows)} shipment lines pulled; Sky's sheet "
                               f"annotated for {_n} SKUs. Reopen this box to see the fresh list.")
            except Exception as e:
                st.error(f"Couldn't update right now ({type(e).__name__}). "
                         "Check the 9Yards login and that Sky's sheet is shared with the app.")

# ---- AI daily briefing ----------------------------------------------------
_ai_csv = ai.table(df)


@st.cache_data(ttl=86400, show_spinner="🤖 Writing today's briefing…")
def cached_briefing(csv, ship_n, reorder_n, overdue_n, _stamp):
    return ai.daily_briefing(csv, ship_n, reorder_n, overdue_n)


with st.expander("📰  Today's AI briefing", expanded=False):
    if not ai.have_key():
        st.info("🤖 Add your free Gemini key to switch this on — see the **🤖 Ask AI** tab for setup steps.")
    elif not st.session_state.get("brief_ready"):
        # Don't call the AI on page load — keep the dashboard snappy. Generate on click.
        st.caption("Click to generate today's plain-English summary (takes a few seconds).")
        if st.button("✨ Generate today's briefing", key="brief_go"):
            st.session_state["brief_ready"] = True
            st.rerun()
    else:
        try:
            st.markdown(cached_briefing(_ai_csv, len(ship), len(reorder), n_overdue, ago or "live"))
            if st.button("↻ Regenerate", key="brief_regen"):
                cached_briefing.clear()
                st.rerun()
        except Exception as e:
            st.warning(f"Couldn't generate the briefing right now ({type(e).__name__}). "
                       "Check the API key on the **🤖 Ask AI** tab.")

ppc_df = load_ppc()
_n_ppc = len(ppc_df) if not ppc_df.empty else 0
tab_ship, tab_order, tab_all, tab_ads, tab_ai = st.tabs(
    [f"🚢 Ship to FBA · {len(ship)}", f"🏭 Reorder · {len(reorder)}",
     f"📋 All products · {len(df)}",
     (f"📣 Ads · {_n_ppc}" if _n_ppc else "📣 Ads"), "🤖 Ask AI"])

def _cbm_unit(r):
    try:
        return float(r.get("CBM/unit", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def ship_group(frame, title):
    """Render one shipment group (Standard or Oversize) with a live CBM total."""
    if frame.empty:
        return
    skus = [str(s) for s in frame["SKU"]]
    paste = "\n".join(f"{s}\t{int(st.session_state['shq_'+s])}"
                      for s in skus if int(st.session_state["shq_" + s]) > 0)
    tot_cbm = sum(_cbm_unit(r) * int(st.session_state["shq_" + str(r["SKU"])]) for _, r in frame.iterrows())
    n_units = sum(int(st.session_state["shq_" + s]) for s in skus)
    st.markdown(f"#### {title} &nbsp;·&nbsp; {len(frame)} SKUs &nbsp;·&nbsp; "
                f"{n_units:,} units &nbsp;·&nbsp; 📦 **{tot_cbm:.2f} CBM**")
    copy_button(paste, label=f"📋  Copy {title} for 9Yards")
    with st.expander("…or copy manually"):
        st.code(paste or "(nothing to ship)", language=None)
    for _, r in frame.iterrows():
        sku = str(r["SKU"])
        c1, c2, c3 = st.columns([1, 4.3, 1.8], vertical_alignment="center")
        with c1:
            if str(r.get("Image", "")).startswith("http"):
                st.image(r["Image"], width=58)
        with c2:
            asin = str(r.get("ASIN", "")).strip()
            amz = f"https://www.amazon.com/dp/{asin}" if asin else ""
            title_ = f"[{str(r['Product'])[:60]}]({amz})" if amz else str(r["Product"])[:60]
            st.markdown(f"**{title_}**")
            bits = [f"[{sku}]({seller_central_url(sku)})", f"🏭 {r['Supplier']}"]
            if amz:
                bits.append(f"[🛒 {asin}]({amz})")
            bits += [f"FBA {_int(r['FBA days left'])}d left", f"China {_int(r['China warehouse']):,}",
                     f"cover {_int(r['Days of cover'])}d"]
            st.caption(" · ".join(bits))
            why = str(r.get("Why ship", "")).strip()
            if why:
                with st.expander("Why this number?"):
                    st.write(why)
        with c3:
            st.number_input("Ship qty", min_value=0, step=10, key="shq_" + sku)
            cu = _cbm_unit(r)
            st.caption(f"📦 {cu * int(st.session_state['shq_'+sku]):.2f} CBM" if cu > 0 else "CBM n/a")


def push_ship_to_sky(china_skus, ship_map):
    """Write ship quantities into column F ('ship') of Sky's sheet, matched BY SKU (row-safe).
    Only rows whose SKU we track are touched: the quantity for what you're shipping, blank for
    the rest — so Sky's 'ship' column shows exactly this round's plan. Nothing else is changed.
    Returns (n_written, n_cleared)."""
    sh = _gclient().open_by_key(config.SKY_SHEET_ID)
    written = cleared = 0
    for ws in sh.worksheets():
        vals = ws.get_all_values()
        if len(vals) < 3:
            continue
        hdr = [str(h).strip().lower() for h in vals[0]]
        sku_c = next((i for i, h in enumerate(hdr) if h in ("sku name", "sku")), 1)
        updates = []
        for ridx, row in enumerate(vals[2:], start=3):   # data starts on sheet row 3
            s = row[sku_c].strip() if len(row) > sku_c else ""
            if not s or s not in china_skus:
                continue
            q = ship_map.get(s, 0)
            updates.append({"range": f"F{ridx}", "values": [[q if q > 0 else ""]]})
            written += 1 if q > 0 else 0
            cleared += 0 if q > 0 else 1
        if updates:
            ws.batch_update(updates, value_input_option="USER_ENTERED")
    return written, cleared


with tab_ship:
    if ship.empty:
        st.success("Nothing to ship right now. ✅")
    else:
        for sku, q in zip([str(s) for s in ship["SKU"]], ship["Ship qty"]):
            st.session_state.setdefault("shq_" + sku, _int(q))
        st.caption("Adjust any quantity (use +/– or type), then hit the green button → paste into "
                   "9Yards → Add SKU → **Paste Bulk**. CBM totals update as you change quantities.")
        if "Size" in ship.columns:
            _is_ovr = ship["Size"].astype(str).str.strip().str.lower().eq("oversize")
        else:
            _is_ovr = pd.Series(False, index=ship.index)
        std_f, ovr_f = ship[~_is_ovr], ship[_is_ovr]
        sub_std, sub_ovr = st.tabs([f"📦 Standard · {len(std_f)}", f"🛒 Oversize · {len(ovr_f)}"])
        with sub_std:
            if std_f.empty:
                st.success("No standard-size items to ship right now. ✅")
            else:
                ship_group(std_f, "📦 Standard size")
        with sub_ovr:
            if ovr_f.empty:
                st.success("No oversize items to ship right now. ✅")
            else:
                ship_group(ovr_f, "🛒 Oversize")

        with st.expander("🚀 Send ship quantities to Sky's sheet"):
            _ship_map = {str(s): int(st.session_state.get("shq_" + str(s), 0)) for s in ship["SKU"]}
            _ship_map = {k: v for k, v in _ship_map.items() if v > 0}
            st.caption("This writes your quantities straight into the **'ship' column** of Sky's sheet, "
                       "matched by SKU — so Sky sees exactly what to prepare. It sets the quantities you're "
                       "shipping and blanks the rest of your tracked SKUs (so it's this round's plan). "
                       "Nothing else in Sky's sheet is touched.")
            if not _ship_map:
                st.info("No ship quantities set yet — adjust some above first.")
            else:
                st.write(f"**{len(_ship_map)} SKUs** will be sent to Sky:")
                st.dataframe(pd.DataFrame([{"SKU": k, "Ship qty": v} for k, v in _ship_map.items()]),
                             hide_index=True, use_container_width=True)
                if st.button("🚀 Send to Sky's sheet now", type="primary"):
                    with st.spinner("Writing to Sky's sheet…"):
                        try:
                            w, c = push_ship_to_sky(set(df["SKU"].astype(str)), _ship_map)
                            st.success(f"✅ Done — wrote **{w}** ship quantities into Sky's sheet"
                                       + (f" and cleared {c} old ones." if c else "."))
                        except Exception as e:
                            st.error(f"Couldn't write to Sky's sheet ({type(e).__name__}). On the cloud site "
                                     "the app's service account needs **Editor** access to Sky's sheet — share it "
                                     "with `kitchentoolz-app@kitchentoolz-inventory.iam.gserviceaccount.com`.")

def supplier_filter(frame, key):
    sups = sorted(s for s in frame["Supplier"].unique() if str(s).strip() and s != "—")
    if not sups:
        return frame
    pick = st.selectbox("Supplier", ["All suppliers"] + sups, key=key)
    return frame if pick == "All suppliers" else frame[frame["Supplier"] == pick]

with tab_order:
    st.caption("Products whose whole pipeline won't cover the next make-and-ship cycle. "
               "Each card says how many to order, by when, and why — click a product name for the full breakdown.")
    rv = supplier_filter(reorder, "sup_reorder")
    render(rv,
           lambda r: f'<div class="kt-actnum" style="color:{"#c0392b" if r["Priority"]=="order now" else "#9a7400"}">'
                     f'Order {_int(r["Order qty"]):,}</div>', "Why order")

with tab_all:
    st.caption("Every tracked product. **Click a product name** for its full breakdown — "
               "every unit, the math, and its shipments.")
    c_search, c_sup = st.columns([3, 1])
    with c_search:
        q = st.text_input("🔎 Search by product name, SKU, or ASIN",
                          placeholder="e.g. cookie jar, SK-SW-…, B0DZW6QKG1")
    with c_sup:
        sups = sorted(s for s in df["Supplier"].unique() if str(s).strip() and s != "—")
        pick = st.selectbox("Supplier", ["All suppliers"] + sups, key="sup_all")
    view = df if pick == "All suppliers" else df[df["Supplier"] == pick]
    if q:
        ql = q.lower()
        view = view[view.apply(lambda r: ql in str(r["Product"]).lower() or ql in str(r["SKU"]).lower()
                               or ql in str(r.get("ASIN", "")).lower(), axis=1)]
    render(view, lambda r: f'<div class="kt-actnum" style="font-size:1.05rem">{EMOJI.get(str(r.get("Priority","")),"")} '
                           f'{html.escape(str(r.get("What to do","")))}</div>', "Why order")

with tab_ads:
    show_ads(ppc_df)


@st.cache_data(ttl=86400, show_spinner="🤖 Thinking up product ideas…")
def cached_ideas(csv, _stamp):
    return ai.product_ideas(csv)


@st.cache_data(ttl=86400, show_spinner="🔎 Researching the market on the web… (~30s)")
def cached_research(csv, focus, _stamp):
    return ai.research(csv, focus)


with tab_ai:
    if not ai.have_key():
        st.subheader("🤖 Turn on the AI assistant")
        st.markdown(
            "The AI briefing, chat, and product ideas use **Google Gemini's free tier**. "
            "Grab a free key (no credit card) and paste it in:\n\n"
            "1. Go to **https://aistudio.google.com/apikey** and sign in with your Google account.\n"
            "2. Click **Create API key** → copy it (starts with `AIza…`).\n"
            "3. **Local PC:** create a file `.streamlit/secrets.toml` next to the app with:\n"
            "   ```toml\n   gemini_api_key = \"AIza-your-key-here\"\n   ```\n"
            "   **Cloud (the shared site):** Streamlit → Manage app → **Settings → Secrets**, "
            "paste the same line, save.\n"
            "4. Refresh — this tab turns into a chat box.\n\n"
            "_Free at your volume. (Want top quality instead? A paid Anthropic key also works — "
            "set `anthropic_api_key` instead.)_")
    else:
        st.caption("Ask anything about your inventory — it answers from your live data.")
        if "chat" not in st.session_state:
            st.session_state.chat = []
        for role, content in st.session_state.chat:
            with st.chat_message(role):
                st.markdown(content)
        prompt = st.chat_input("e.g. What should I order this week? What's most at risk of selling out?")
        if prompt:
            st.session_state.chat.append(("user", prompt))
            with st.chat_message("user"):
                st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking…"):
                    try:
                        reply = ai.answer(_ai_csv, prompt, st.session_state.chat[:-1])
                    except Exception as e:
                        reply = f"Sorry — I couldn't answer just now ({type(e).__name__}). Check the API key."
                st.markdown(reply)
            st.session_state.chat.append(("assistant", reply))
        if st.session_state.chat:
            cc1, _ = st.columns([1, 3])
            with cc1:
                if st.button("🧹 Clear chat", use_container_width=True):
                    st.session_state.chat = []
                    st.rerun()

        with st.expander("🧰 More AI tools — product ideas & market research"):
            st.markdown("**💡 New-product ideas** — quick suggestions from your own catalog. Instant.")
            if st.button("✨ Suggest product ideas"):
                try:
                    st.markdown(cached_ideas(_ai_csv, ago or "live"))
                except Exception as e:
                    st.warning(f"Couldn't generate ideas right now ({type(e).__name__}).")

            st.divider()
            st.markdown("**🔎 Market research (web)** — trends, competitors, gaps, review complaints, tied "
                        "back to your line. ~30s. Directional only — verify top picks in Helium 10.")
            focus = st.text_input("Optional — narrow the focus",
                                  placeholder="e.g. airtight coffee canisters, glass vs acrylic")
            if st.button("🔎 Research opportunities"):
                try:
                    st.markdown(cached_research(_ai_csv, focus.strip(), ago or "live"))
                except Exception as e:
                    st.warning(f"Couldn't run web research right now ({type(e).__name__}). "
                               "The free tier may limit web searches — the catalog ideas always work.")

st.markdown('<div class="kt-foot">KitchenToolz · China Reorder Dashboard · updates every morning</div>',
            unsafe_allow_html=True)
