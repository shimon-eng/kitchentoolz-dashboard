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
  padding:2px 9px; font-size:.72rem; margin-left:7px; font-weight:600; cursor:help; }
.kt-link { color:inherit; text-decoration:none; }
.kt-link:hover { text-decoration:underline; }
.kt-skulink { color:#1f8a70; text-decoration:none; font-weight:600; }
.kt-skulink:hover { text-decoration:underline; }
.kt-mc { cursor:help; }
details.kt-why { margin-top:9px; }
details.kt-why summary { cursor:pointer; color:#1f8a70; font-size:.8rem; font-weight:600; list-style:none; }
details.kt-why summary::before { content:"💡 "; }
details.kt-why div { background:#f7f9fa; border:1px solid #eaeef0; border-radius:10px; padding:11px 13px;
  margin-top:7px; color:#445; font-size:.82rem; white-space:pre-wrap; line-height:1.5; }
.stTabs [data-baseweb="tab-list"] { gap:6px; }
.stTabs [data-baseweb="tab"] { font-weight:600; border-radius:10px 10px 0 0; }
.kt-brand { font-size:.72rem; font-weight:800; letter-spacing:.24em; opacity:.85;
  text-transform:uppercase; margin-bottom:6px; }
.kt-foot { text-align:center; color:#9aa3ad; font-size:.78rem; margin:28px 0 8px; }
.kt-card { border:1px solid #eef0f3; }
.kt-kpi { border:1px solid #eef0f3; }
.kt-card:hover img { transform:scale(1.04); transition:.18s; }
@media (max-width: 640px) {
  .kt-card { flex-wrap:wrap; gap:12px; }
  .kt-act { text-align:left; min-width:100%; margin-top:4px; }
  .kt-kpi { min-width:46%; }
  .block-container { padding-left:.6rem; padding-right:.6rem; }
}
/* —— warm KitchenToolz brand theme —— */
.stApp { background:#f6f3ee; }
.kt-hero { background:linear-gradient(120deg,#3e2723 0%,#7a5239 100%); box-shadow:0 10px 30px rgba(62,39,35,.28); }
.kt-brand { color:#f0e6da; }
.kt-logo { height:48px; margin-bottom:10px; display:block; }
/* stock-breakdown mini-bar */
.kt-bar { display:flex; height:7px; border-radius:99px; overflow:hidden; margin-top:10px; background:#eef0f3; max-width:420px; }
.kt-bar span { height:100%; }
.kt-barkey { font-size:.66rem; color:#9aa0aa; margin-top:4px; }
.kt-barkey i { font-style:normal; }
.kt-dot { display:inline-block; width:8px; height:8px; border-radius:2px; margin:0 3px 0 9px; vertical-align:middle; }
/* product detail page */
.kt-back { color:#7a5239; font-weight:700; text-decoration:none; font-size:.95rem; }
.kt-back:hover { text-decoration:underline; }
.kt-detail { background:#fff; border-radius:18px; padding:8px 4px; }
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
    overdue = (f'<span class="kt-overdue" title="These in-production units are overdue at Sky — chase him">'
               f'⚠️ {_int(row.get("Overdue days"))}d overdue at Sky</span>'
               if _int(row.get("Overdue days")) > 0 else "")
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
    return (
        f'<div class="kt-card">{imgtag}<div class="kt-body">'
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


def copy_button(text, label="📋  Copy all for 9Yards"):
    """A big, fancy one-click 'copy to clipboard' button (works inside Streamlit's iframe)."""
    import json as _json
    import streamlit.components.v1 as components
    payload = _json.dumps(text)
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
          document.getElementById('m').innerText = ok ? '✓ Copied! Paste into 9Yards → Paste Bulk.' : 'Select the box below and press Ctrl+C.';
        }}
      </script>
    """, height=62)


def show_detail(df, sku):
    """A full detail 'page' for one product (opened by clicking a product name)."""
    st.markdown('<a class="kt-back" href="?" target="_self">← Back to dashboard</a>', unsafe_allow_html=True)
    m = df[df["SKU"].astype(str) == str(sku)]
    if m.empty:
        st.warning(f"Product '{sku}' isn't on the dashboard right now.")
        return
    r = m.iloc[0]
    st.markdown(f"## {r['Product']}")
    c1, c2 = st.columns([1, 2], vertical_alignment="top")
    with c1:
        if str(r.get("Image", "")).startswith("http"):
            st.image(r["Image"], use_container_width=True)
    with c2:
        emoji = EMOJI.get(str(r.get("Priority", "")), "")
        st.markdown(f"### {emoji} {r.get('What to do', '')}")
        asin = str(r.get("ASIN", "")).strip()
        line = f"`{r['SKU']}` · 🏭 {r['Supplier']}"
        if asin:
            line += f" · [🔗 View on Amazon](https://www.amazon.com/dp/{asin})"
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
    ws, wo = str(r.get("Why ship", "")).strip(), str(r.get("Why order", "")).strip()
    if ws:
        st.markdown("#### 🚢 Why this ship quantity")
        st.info(ws)
    if wo:
        st.markdown("#### 🏭 Why this order quantity")
        st.info(wo)
    if _int(r.get("Overdue days")) > 0:
        st.warning(f"⚠️ {_int(r.get('Overdue days'))} days overdue at the supplier — chase them.")
    st.markdown('<a class="kt-back" href="?" target="_self">← Back to dashboard</a>', unsafe_allow_html=True)


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

# ---- product detail page (when a product name is clicked) -----------------
_view = st.query_params.get("view")
if _view:
    show_detail(df, _view)
    st.stop()

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
ago, stale = freshness(df)
if stale:
    st.markdown(
        '<div style="background:#fff3cd;color:#856404;border-radius:12px;padding:12px 16px;'
        'margin-bottom:14px;font-weight:600;border:1px solid #ffe69c;">⚠️ These numbers may be out of '
        f'date — last refreshed {ago}. Ask Shimon to run the morning update.</div>', unsafe_allow_html=True)
chip = (f"🟢 Updated {ago} · {len(df)} products tracked" if ago else f"🟢 Live data · {len(df)} products tracked")
_logo = logo_uri()
brand = f'<img class="kt-logo" src="{_logo}">' if _logo else '<div class="kt-brand">🍴 KitchenToolz</div>'
st.markdown(
    f'<div class="kt-hero">{brand}'
    '<h1>China Reorder Command Center</h1>'
    '<p>Everything you need to know — what to ship, what to order, and why.</p>'
    f'<span class="kt-chip">{chip}</span></div>',
    unsafe_allow_html=True)

st.markdown(
    '<div class="kt-kpis">'
    f'<div class="kt-kpi" style="--ac:#1f6f3d"><div class="n">{len(ship)}</div><div class="l">🚢 To ship now</div></div>'
    f'<div class="kt-kpi" style="--ac:#c0392b"><div class="n">{len(reorder)}</div><div class="l">🏭 To reorder</div></div>'
    f'<div class="kt-kpi" style="--ac:#e0a800"><div class="n">{n_overdue}</div><div class="l">⚠️ Overdue at Sky</div></div>'
    f'<div class="kt-kpi" style="--ac:#2e86de"><div class="n">{otw_total:,}</div><div class="l">📦 Units on the way</div></div>'
    '</div>', unsafe_allow_html=True)

st.markdown(
    '<div class="kt-barkey">Stock bar on each card: '
    '<span class="kt-dot" style="background:#2e86de"></span><i>In FBA</i>'
    '<span class="kt-dot" style="background:#1f8a70"></span><i>On the way</i>'
    '<span class="kt-dot" style="background:#e0a800"></span><i>China</i>'
    '<span class="kt-dot" style="background:#9b59b6"></span><i>In production</i>'
    '&nbsp;·&nbsp; click a product name for full details</div>', unsafe_allow_html=True)

tab_ship, tab_order, tab_all = st.tabs(
    [f"🚢 Ship to FBA · {len(ship)}", f"🏭 Reorder · {len(reorder)}", f"📋 All products · {len(df)}"])

with tab_ship:
    if ship.empty:
        st.success("Nothing to ship right now. ✅")
    else:
        ship_skus = [str(s) for s in ship["SKU"]]
        for sku, q in zip(ship_skus, ship["Ship qty"]):
            st.session_state.setdefault("shq_" + sku, _int(q))
        paste = "\n".join(f"{sku}\t{int(st.session_state['shq_'+sku])}"
                          for sku in ship_skus if int(st.session_state["shq_" + sku]) > 0)
        copy_button(paste)
        st.caption("Adjust any quantity below (use +/– or type), then hit the green button → paste into "
                   "9Yards → Add SKU → **Paste Bulk**.")
        with st.expander("…or copy manually"):
            st.code(paste or "(nothing to ship)", language=None)
        st.divider()
        for _, r in ship.iterrows():
            sku = str(r["SKU"])
            c1, c2, c3 = st.columns([1, 4.5, 1.6], vertical_alignment="center")
            with c1:
                if str(r.get("Image", "")).startswith("http"):
                    st.image(r["Image"], width=58)
            with c2:
                amz = f"https://www.amazon.com/dp/{r['ASIN']}" if str(r.get("ASIN", "")).strip() else ""
                title = f"[{str(r['Product'])[:64]}]({amz})" if amz else str(r["Product"])[:64]
                st.markdown(f"**{title}**")
                st.caption(f"`{sku}` · 🏭 {r['Supplier']} · FBA {_int(r['FBA days left'])}d left · "
                           f"China {_int(r['China warehouse']):,} · cover {_int(r['Days of cover'])}d")
                why = str(r.get("Why ship", "")).strip()
                if why:
                    with st.expander("Why this number?"):
                        st.write(why)
            with c3:
                st.number_input("Ship qty", min_value=0, step=10, key="shq_" + sku)

def supplier_filter(frame, key):
    sups = sorted(s for s in frame["Supplier"].unique() if str(s).strip() and s != "—")
    if not sups:
        return frame
    pick = st.selectbox("Supplier", ["All suppliers"] + sups, key=key)
    return frame if pick == "All suppliers" else frame[frame["Supplier"] == pick]

with tab_order:
    rv = supplier_filter(reorder, "sup_reorder")
    render(rv,
           lambda r: f'<div class="kt-actnum" style="color:{"#c0392b" if r["Priority"]=="order now" else "#9a7400"}">'
                     f'Order {_int(r["Order qty"]):,}</div>', "Why order")

with tab_all:
    c_search, c_sup = st.columns([3, 1])
    with c_search:
        q = st.text_input("🔎 Search by product name or SKU", placeholder="e.g. cookie jar, SK-SW-…")
    with c_sup:
        sups = sorted(s for s in df["Supplier"].unique() if str(s).strip() and s != "—")
        pick = st.selectbox("Supplier", ["All suppliers"] + sups, key="sup_all")
    view = df if pick == "All suppliers" else df[df["Supplier"] == pick]
    if q:
        ql = q.lower()
        view = view[view.apply(lambda r: ql in str(r["Product"]).lower() or ql in str(r["SKU"]).lower(), axis=1)]
    render(view, lambda r: f'<div class="kt-actnum" style="font-size:1.05rem">{EMOJI.get(str(r.get("Priority","")),"")} '
                           f'{html.escape(str(r.get("What to do","")))}</div>', "Why order")

st.markdown('<div class="kt-foot">KitchenToolz · China Reorder Dashboard · updates every morning</div>',
            unsafe_allow_html=True)
