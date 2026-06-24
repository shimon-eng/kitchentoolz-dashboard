"""AI features for the Kitchentoolz dashboard.

Three things:
  1. daily_briefing()  → a short plain-English "what matters today" bulletin
  2. answer()          → conversational Q&A grounded in the live inventory data
  3. product_ideas()   → catalog-based expansion suggestions

Provider-flexible. It uses whichever key you've set:
  • Google Gemini  — free tier. Key in st.secrets["gemini_api_key"] or env GEMINI_API_KEY.
  • Anthropic Claude — paid. Key in st.secrets["anthropic_api_key"] or env ANTHROPIC_API_KEY.
If both are set, Gemini is preferred (it's the free one). Everything degrades
gracefully when no key is present — have_key() lets the app show a setup message
instead of crashing.
"""
import os

import streamlit as st

# Free, good-enough default for Gemini; override with st.secrets["gemini_model"].
GEMINI_MODEL = "gemini-2.5-flash"
# Best-quality default for Claude; override with st.secrets["ai_model"].
ANTHROPIC_MODEL = "claude-opus-4-8"

# Only the decision-relevant columns get sent to the model — keeps it focused and cheap.
_COLS = ["SKU", "Product", "Supplier", "Priority", "What to do", "Sells per day",
         "In FBA", "FBA days left", "China warehouse", "On the way", "In production",
         "Days of cover", "Ship qty", "Order qty", "Order by", "Overdue days"]

_DATA_NOTE = ("The data below is one row per product, live from the dashboard. "
              "Columns: FBA days left = days of Amazon stock at current sales pace; "
              "China warehouse = units ready at the supplier; On the way = units already "
              "heading to Amazon; In production = units being made; Days of cover = how long "
              "the whole pipeline lasts; Ship qty / Order qty = the dashboard's suggestions; "
              "Overdue days = how late the supplier is on in-production units.")


def _secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


def _gemini_key():
    return _secret("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def _anthropic_key():
    return _secret("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")


def _provider():
    """Which AI backend to use, based on the configured key. Gemini (free) wins."""
    if _gemini_key():
        return "gemini"
    if _anthropic_key():
        return "anthropic"
    return None


def have_key():
    return _provider() is not None


def table(df):
    """Compact CSV of the decision-relevant columns — what we feed the model."""
    cols = [c for c in _COLS if c in df.columns]
    return df[cols].to_csv(index=False)


def _generate(prefix, csv, turns, max_tokens):
    """Run one request. turns is a list of (role, text), role in {'user','assistant'}."""
    data_text = _DATA_NOTE + "\n\nDATA:\n" + csv
    provider = _provider()

    if provider == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=_gemini_key())
        contents = [{"role": ("model" if r == "assistant" else "user"), "parts": [{"text": t}]}
                    for r, t in turns]
        cfg = types.GenerateContentConfig(
            system_instruction=prefix + "\n\n" + data_text,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),  # faster/cheaper, plenty for this
        )
        resp = client.models.generate_content(
            model=_secret("gemini_model") or GEMINI_MODEL, contents=contents, config=cfg)
        return (resp.text or "").strip()

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=_anthropic_key())
        msg = client.messages.create(
            model=_secret("ai_model") or ANTHROPIC_MODEL, max_tokens=max_tokens,
            system=[{"type": "text", "text": prefix},
                    {"type": "text", "text": data_text, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": r, "content": t} for r, t in turns])
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    raise RuntimeError("No AI key configured")


# ---------------------------------------------------------------- daily briefing
_BRIEF_SYS = (
    "You are the inventory analyst for Kitchentoolz, an Amazon seller that manufactures "
    "kitchen storage products (glass jars, mason jars, cookie jars, canisters) in China. "
    "You write a short morning briefing for the owner Shimon and his partner Avi, who are "
    "not analysts. Be concrete, prioritized, and plain-spoken. Lead with the single most "
    "important thing. Use short bullet points, each starting with a relevant emoji. Name "
    "specific products and real numbers from the data. Never invent data that isn't there. "
    "Keep the whole briefing under about 180 words.")


def daily_briefing(csv, ship_n, reorder_n, overdue_n):
    req = (f"Today's counts: {ship_n} products need shipping to Amazon FBA now, "
           f"{reorder_n} need a new factory order, {overdue_n} are overdue at the supplier. "
           "Write today's briefing — what should Shimon and Avi focus on today, and why?")
    return _generate(_BRIEF_SYS, csv, [("user", req)], 900)


# ---------------------------------------------------------------- conversational Q&A
_CHAT_SYS = (
    "You are the inventory assistant for Kitchentoolz, an Amazon seller of kitchen storage "
    "products made in China. Answer the user's questions using ONLY the live data table in "
    "this system prompt. Be concise and concrete — cite specific product names and numbers. "
    "If the data doesn't contain the answer, say so plainly rather than guessing. The user "
    "(Shimon or his partner Avi) is not technical, so keep it simple and practical.")


def answer(csv, question, history=None):
    """history is a list of (role, content) tuples for follow-up context."""
    turns = list(history or []) + [("user", question)]
    return _generate(_CHAT_SYS, csv, turns, 1000)


# ---------------------------------------------------------------- product ideas
_IDEAS_SYS = (
    "You are a product strategist for Kitchentoolz, an Amazon seller of kitchen storage "
    "products (glass jars, mason jars, cookie jars, canisters, airtight containers) made in "
    "China. Using the current catalog and sales velocity in the data, suggest expansion "
    "ideas: new sizes, multipacks/bundles, color or material variants, and obvious gaps. "
    "Prioritize ideas adjacent to the best sellers (highest 'Sells per day'). For each idea "
    "give: the idea, a one-line WHY tied to a specific current product and its velocity, and "
    "a rough effort (easy / medium / hard). Give 5-8 ideas, grouped sensibly. Be concrete. "
    "End with one short sentence reminding the reader these are catalog-based suggestions, "
    "not validated market research.")


def product_ideas(csv):
    req = "Suggest product expansion ideas based on this catalog and its sales velocity."
    return _generate(_IDEAS_SYS, csv, [("user", req)], 1500)


# ---------------------------------------------------------------- web research
_RESEARCH_SYS = (
    "You are a product researcher for Kitchentoolz, an Amazon seller of kitchen storage "
    "products (glass jars, mason jars, cookie jars, canisters, airtight containers) made in "
    "China. Use web search to research the CURRENT market: trending products and materials in "
    "kitchen storage, what competitors sell well on Amazon, underserved gaps and niches, common "
    "complaints in reviews you could fix with a better product, and realistic price ranges. "
    "Ground findings in what you actually find online and be specific. Then connect each "
    "opportunity back to Kitchentoolz's existing catalog and best sellers (in the data). "
    "Give 5-7 concrete opportunities, each with: the opportunity, what you found (evidence), how "
    "it fits our line, and rough effort (easy/medium/hard). Be honest about uncertainty. End with "
    "one line noting this is directional research, not validated demand data, and that top picks "
    "should be verified in a tool like Helium 10.")


def _gemini_sources(resp):
    out, seen = [], set()
    try:
        gm = resp.candidates[0].grounding_metadata
        for ch in (gm.grounding_chunks or []):
            w = getattr(ch, "web", None)
            if w and getattr(w, "uri", None) and w.uri not in seen:
                seen.add(w.uri)
                out.append((w.title or w.uri, w.uri))
    except Exception:
        pass
    return out[:8]


def research(csv, focus=""):
    """Web-grounded product research. Gemini uses Google Search; Claude uses web_search."""
    provider = _provider()
    data_text = _DATA_NOTE + "\n\nOUR CATALOG:\n" + csv
    user = "Research new product and improvement opportunities for our kitchen-storage line."
    if focus.strip():
        user += f" Focus especially on: {focus.strip()}."

    if provider == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=_gemini_key())
        cfg = types.GenerateContentConfig(
            system_instruction=_RESEARCH_SYS + "\n\n" + data_text,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=3000)
        resp = client.models.generate_content(
            model=_secret("gemini_model") or GEMINI_MODEL, contents=user, config=cfg)
        text = (resp.text or "").strip()
        srcs = _gemini_sources(resp)
        if srcs:
            text += "\n\n**Sources:**\n" + "\n".join(f"- [{t}]({u})" for t, u in srcs)
        return text

    if provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=_anthropic_key())
        msg = client.messages.create(
            model=_secret("ai_model") or ANTHROPIC_MODEL, max_tokens=3000,
            system=_RESEARCH_SYS + "\n\n" + data_text,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    raise RuntimeError("No AI key configured")
