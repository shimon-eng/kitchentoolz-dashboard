"""Kitchentoolz reorder dashboard — a polished web app built with Streamlit.

Reads the live 'App Data' tab from the dashboard workbook. Run locally with:
    streamlit run streamlit_app.py
"""
import html
from datetime import date

import gspread
import pandas as pd
import streamlit as st

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

st.set_page_config(page_title="Kitchentoolz Reorder", page_icon="📦", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown { font-family: 'Inter', sans-serif; }
.stApp { background: #eef1f5; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1120px; }
#MainMenu, footer, header { visibility: hidden; }

.kt-hero { background: linear-gradient(120deg,#0f3d5e 0%,#1f8a70 100%); color:#fff;
  border-radius:20px; padding:24px 28px; margin-bottom:18px; box-shadow:0 10px 30px rgba(15,61,94,.25); }
.kt-hero h1 { margin:0; font-size:1.8rem; font-weight:800; letter-spacing:-.02em; }
.kt-hero p { margin:6px 0 0; opacity:.9; font-size:.95rem; }
.kt-chip { display:inline-block; background:rgba(255,255,255,.18); padding:5px 13px; border-radius:999px;
  font-size:.8rem; margin-top:12px; font-weight:500; }

.kt-kpis { display:flex; gap:14px; margin-bottom:20px; flex-wrap:wrap; }
.kt-kpi { flex:1; min-width:150px; background:#fff; border-radius:16px; padding:18px 20px;
  box-shadow:0 2px 12px rgba(0,0,0,.05); border-top:4px solid var(--ac,#1f8a70); }
.kt-kpi .n { font-size:2rem; font-weight:800; line-height:1; color:#16202e; }
.kt-kpi .l { color:#7a8290; font-size:.74rem; margin-top:7px; text-transform:uppercase; letter-spacing:.05em; font-weight:600; }

.kt-card { background:#fff; border-radius:16px; padding:15px 18px; margin-bottom:13px;
  box-shadow:0 2px 12px rgba(0,0,0,.05); display:flex; gap:18px; align-items:center; transition:.18s; }
.kt-card:hover { box-shadow:0 10px 28px rgba(0,0,0,.13); transform:translateY(-2px); }
.kt-card img { width:84px; height:84px; object-fit:contain; border-radius:12px; background:#f3f4f6; padding:5px; }
.kt-noimg { width:84px; height:84px; border-radius:12px; background:#f3f4f6; }
.kt-body { flex:1; min-width:0; }
.kt-title { font-weight:700; font-size:1.02rem; color:#16202e; line-height:1.25; }
.kt-sub { color:#8a8f99; font-size:.8rem; margin-top:3px; }
.kt-chips { margin-top:9px; }
.kt-mc { display:inline-block; background:#f1f3f6; color:#566; border-radius:8px; padding:3px 9px;
  font-size:.72rem; margin-right:6px; margin-top:5px; font-weight:500; }
.kt-act { text-align:right; min-width:130px; }
.kt-actnum { font-size:1.5rem; font-weight:800; letter-spacing:-.02em; }
.kt-by { color:#9aa0aa; font-size:.78rem; margin-top:2px; }
.kt-pill { display:inline-block; padding:3px 11px; border-radius:999px; font-size:.72rem; font-weight:700; }
.kt-now { background:#ffe1e1; color:#c0392b; }
.kt-soon { background:#fff2cf; color:#9a7400; }
.kt-ok { background:#e0f3e3; color:#2e7d32; }
.kt-none { background:#ececec; color:#888; }
.kt-overdue { display:inline-block; background:#fff3cd; color:#856404; border-radius:8px;
  padding:2px 9px; font-size:.72rem; margin-left:7px; font-weight:600; }
details.kt-why { margin-top:9px; }
details.kt-why summary { cursor:pointer; color:#1f8a70; font-size:.8rem; font-weight:600; list-style:none; }
details.kt-why summary::before { content:"💡 "; }
details.kt-why div { background:#f7f9fa; border:1px solid #eaeef0; border-radius:10px; padding:11px 13px;
  margin-top:7px; color:#445; font-size:.82rem; white-space:pre-wrap; line-height:1.5; }
.stTabs [data-baseweb="tab-list"] { gap:6px; }
.stTabs [data-baseweb="tab"] { font-weight:600; border-radius:10px 10px 0 0; }
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


@st.cache_data(ttl=300)
def load_discontinued():
    try:
        ws = _gclient().open_by_key(config.CHINA_SHEET_ID).worksheet("Discontinued")
        return {str(r.get("SKU", "")).strip() for r in ws.get_all_records() if str(r.get("SKU", "")).strip()}
    except Exception:
        return set()


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


def card_html(row, action_html, why_field):
    prio = str(row.get("Priority", ""))
    pill_cls, pill_txt = PILL.get(prio, ("kt-none", prio.upper()))
    img = str(row.get("Image", ""))
    imgtag = f'<img src="{html.escape(img)}">' if img.startswith("http") else '<div class="kt-noimg"></div>'
    chips = "".join(f'<span class="kt-mc">{c}</span>' for c in [
        f"Sells {row.get('Sells per day','')}/day",
        f"FBA {_int(row.get('FBA days left'))}d left",
        f"China {_int(row.get('China warehouse')):,}",
        f"On the way {_int(row.get('On the way')):,}",
        f"Cover {_int(row.get('Days of cover'))}d",
    ])
    overdue = (f'<span class="kt-overdue">⚠️ {_int(row.get("Overdue days"))}d overdue at Sky</span>'
               if _int(row.get("Overdue days")) > 0 else "")
    why = str(row.get(why_field, "")).strip()
    why_html = (f'<details class="kt-why"><summary>Why this number?</summary>'
                f'<div>{html.escape(why)}</div></details>') if why else ""
    by = (f'<div class="kt-by">by {html.escape(str(row.get("Order by","")))}</div>'
          if str(row.get("Order by", "")).strip() else "")
    return (
        f'<div class="kt-card">{imgtag}<div class="kt-body">'
        f'<div><span class="kt-pill {pill_cls}">{pill_txt}</span>{overdue}</div>'
        f'<div class="kt-title">{html.escape(str(row.get("Product","")))}</div>'
        f'<div class="kt-sub">{html.escape(str(row.get("SKU","")))} &nbsp;·&nbsp; 🏭 {html.escape(str(row.get("Supplier","")))}</div>'
        f'<div class="kt-chips">{chips}</div>{why_html}</div>'
        f'<div class="kt-act">{action_html}{by}</div></div>'
    )


def render(rows, action_fn, why_field):
    if not len(rows):
        st.success("Nothing here right now. ✅")
        return
    st.markdown("".join(card_html(r, action_fn(r), why_field) for _, r in rows.iterrows()),
                unsafe_allow_html=True)


# ---- load + refresh -------------------------------------------------------
top_l, top_r = st.columns([5, 1])
with top_r:
    if st.button("🔄 Refresh", use_container_width=True):
        load_data.clear()
        st.rerun()

df = load_data()
disc = load_discontinued()
if disc:
    df = df[~df["SKU"].astype(str).str.strip().isin(disc)].copy()

# ---- sidebar: hide / restore discontinued products ------------------------
with st.sidebar:
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
st.markdown(
    '<div class="kt-hero"><h1>📦 Kitchentoolz — China Reorder</h1>'
    '<p>Your live command center for what to ship and what to order.</p>'
    f'<span class="kt-chip">🟢 Live data · {len(df)} products tracked</span></div>',
    unsafe_allow_html=True)

st.markdown(
    '<div class="kt-kpis">'
    f'<div class="kt-kpi" style="--ac:#1f6f3d"><div class="n">{len(ship)}</div><div class="l">🚢 To ship now</div></div>'
    f'<div class="kt-kpi" style="--ac:#c0392b"><div class="n">{len(reorder)}</div><div class="l">🏭 To reorder</div></div>'
    f'<div class="kt-kpi" style="--ac:#e0a800"><div class="n">{n_overdue}</div><div class="l">⚠️ Overdue at Sky</div></div>'
    f'<div class="kt-kpi" style="--ac:#2e86de"><div class="n">{otw_total:,}</div><div class="l">📦 Units on the way</div></div>'
    '</div>', unsafe_allow_html=True)

tab_ship, tab_order, tab_all = st.tabs(
    [f"🚢 Ship to FBA · {len(ship)}", f"🏭 Reorder · {len(reorder)}", f"📋 All products · {len(df)}"])

with tab_ship:
    render(ship, lambda r: f'<div class="kt-actnum" style="color:#1f6f3d">Ship {_int(r["Ship qty"]):,}</div>', "Why ship")

with tab_order:
    render(reorder,
           lambda r: f'<div class="kt-actnum" style="color:{"#c0392b" if r["Priority"]=="order now" else "#9a7400"}">'
                     f'Order {_int(r["Order qty"]):,}</div>', "Why order")

with tab_all:
    q = st.text_input("🔎 Search by product name or SKU", placeholder="e.g. cookie jar, SK-SW-…")
    view = df
    if q:
        ql = q.lower()
        view = df[df.apply(lambda r: ql in str(r["Product"]).lower() or ql in str(r["SKU"]).lower(), axis=1)]
    render(view, lambda r: f'<div class="kt-actnum" style="font-size:1.05rem">{EMOJI.get(str(r.get("Priority","")),"")} '
                           f'{html.escape(str(r.get("What to do","")))}</div>', "Why order")
