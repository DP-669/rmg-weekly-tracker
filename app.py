import streamlit as st
import streamlit.components.v1 as components
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date, timedelta
import uuid

from core import (
    COLS,
    format_week,
    get_monday,
    is_transient,
    linkify,
    next_status,
    plan_rollover,
    retry,
    sort_items,
)


st.set_page_config(page_title="rMG Weekly", layout="wide", page_icon="📋")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=DM+Sans:wght@400;500;600&display=swap');

:root {
    --fs-scale: 1;

    /* Legibility tokens. Defaults fix two real contrast failures: item text was
       inheriting Streamlit's 400-weight default, and "done" rows plus the row
       numbers sat at #8E8E93 — 3.3:1 on white, under the 4.5:1 AA floor for
       body text. The [data-legible="1"] block below goes further for anyone who
       wants it; the toggle sits in the text-size pill. */
    --item-color: #1C1C1E;      /* 17.0:1 */
    --item-weight: 500;
    --muted-color: #636366;     /* 6.0:1 — secondary, but readable */
    --muted-weight: 400;
    --link-color: #0B5FCC;      /* 6.0:1 (was #007AFF at 4.0:1) */
    --line-height: 1.5;
    --tracking: 0;
    --font-stack: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

    /* Surfaces. Named so the dark palette is one override block, not a rewrite. */
    --page-bg: #F2F2F7;
    --surface: #FFFFFF;
    --surface-2: #F9F9FB;
    --border: #E5E5EA;
    --accent: #007AFF;
    --accent-orange: #FF9500;
    --accent-green: #34C759;
    --accent-yellow: #FFD60A;
    --pill-bg: rgba(255, 255, 255, 0.96);
    /* Widget chrome — checkbox labels, buttons, the week label — scales at half
       rate. Row layout is fixed-ratio columns, and at full scale "In progress"
       breaks to one letter per line inside its column. Content (item text,
       names, numbering) still takes the full scale, which is what is actually
       being read. */
    --fs-chrome: calc(1 + (var(--fs-scale) - 1) * 0.5);
}

/* High-legibility mode: maximum contrast, heavier strokes, more air between
   lines. Kept as a switch rather than the default because it trades the app's
   lighter look for readability, and that is a personal call. */
:root[data-legible="1"] {
    --item-color: #000000;      /* 21.0:1 */
    --item-weight: 600;
    --muted-color: #3A3A3C;     /* 11.4:1 */
    --muted-weight: 500;
    --link-color: #0A4FA8;      /* 8.6:1 */
    --line-height: 1.65;
    --tracking: 0.01em;
    /* Atkinson Hyperlegible was drawn by the Braille Institute specifically for
       low vision: exaggerated letterform differences so b/d, p/q, I/l/1 and O/0
       cannot be confused. It ships Regular and Bold only, hence 700 not 600. */
    --font-stack: 'Atkinson Hyperlegible', 'DM Sans', -apple-system, sans-serif;
    --item-weight: 700;
    --muted-weight: 400;
}

/* ── Dark mode ────────────────────────────────────────────────────────────
   Only colours change here; weight, line-height and typeface come from the
   blocks above so the two switches compose instead of overriding each other. */
:root[data-theme="dark"] {
    --page-bg: #000000;
    --surface: #1C1C1E;
    --surface-2: #2C2C2E;
    --border: #38383A;
    --item-color: #F2F2F7;      /* 15.3:1 on #1C1C1E */
    --muted-color: #A1A1A6;     /* 6.6:1 */
    --link-color: #6CB4FF;      /* 8.0:1 */
    --accent: #0A84FF;
    --accent-orange: #FF9F0A;
    --accent-green: #30D158;
    --accent-yellow: #FFD60A;
    --pill-bg: rgba(44, 44, 46, 0.96);
}

:root[data-theme="dark"][data-legible="1"] {
    --item-color: #FFFFFF;      /* 16.7:1 */
    --muted-color: #C7C7CC;     /* 11.0:1 */
    --link-color: #8FC7FF;      /* 10.6:1 */
}

/* Links were #007AFF — 4.0:1, under the AA floor. */
.block-container a { color: var(--link-color) !important; text-decoration: underline; }
:root[data-legible="1"] .block-container a { font-weight: 600; }

/* In high-legibility mode the widget labels take the item colour too, not just
   the item text. This must be the token, never a literal: hardcoding #000 here
   turned the person names black-on-black once dark mode existed. */
:root[data-legible="1"] [data-testid="stCheckbox"] label,
:root[data-legible="1"] .stRadio label,
:root[data-legible="1"] [data-testid="stExpander"] summary {
    color: var(--item-color) !important;
    font-weight: var(--item-weight) !important;
}

/* Streamlit sizes its own widget text in rem, so the root size drives every
   label this stylesheet never touches. */
html { font-size: calc(16px * var(--fs-chrome)) !important; }

html, body, [class*="css"] {
    font-family: var(--font-stack) !important;
    background-color: var(--page-bg) !important;
}
/* Streamlit sets font-family directly on stMarkdownContainer, which outranks
   anything inherited from body — which is why the app's typeface never actually
   reached the item text. Material ligature icons live outside these containers,
   but are excluded explicitly so a Streamlit change cannot turn them into the
   literal word "keyboard_arrow_down". */
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] *:not([data-testid="stIconMaterial"]),
[data-testid="stCheckbox"] label,
.stRadio label,
.stButton > button,
.stTextInput input,
[data-testid="stWidgetLabel"] {
    font-family: var(--font-stack) !important;
}
[data-testid="stIconMaterial"] {
    font-family: "Material Symbols Rounded", "Material Icons" !important;
}

/* Streamlit paints its own app shell; without this the page stays light. */
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stHeader"] {
    background-color: var(--page-bg) !important;
}
body { font-size: calc(15px * var(--fs-scale)) !important; }
#MainMenu, header, footer { visibility: hidden; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: calc(1040px * var(--fs-scale)); }

/* Top bar */
.top-bar {
    display: flex;
    align-items: center;
    gap: 24px;
    background: var(--surface);
    border-radius: 10px;
    border: 1px solid var(--border);
    padding: 10px 16px;
    margin-bottom: 18px;
    flex-wrap: wrap;
}

/* Person section */
.person-header {
    font-size: calc(17px * var(--fs-scale));
    font-weight: 600;
    color: var(--item-color);
    padding: 6px 0 2px 0;
    border-bottom: 2px solid var(--accent);
    margin-bottom: 8px;
    margin-top: 16px;
}
.person-header-mine {
    font-size: calc(17px * var(--fs-scale));
    font-weight: 600;
    color: var(--accent);
    padding: 6px 0 2px 0;
    border-bottom: 2px solid #007AFF;
    margin-bottom: 8px;
    margin-top: 16px;
}

/* Item rows */
.item-row {
    display: flex;
    align-items: center;
    background: var(--surface);
    border-radius: 8px;
    border: 1px solid var(--border);
    padding: 8px 12px;
    margin-bottom: 4px;
    font-size: calc(15px * var(--fs-scale));
}
.item-done {
    text-decoration: line-through;
    color: #8E8E93;
}

/* Default buttons */
.stButton > button {
    border-radius: 7px !important;
    font-size: calc(14px * var(--fs-chrome)) !important;
    padding: 4px 12px !important;
    height: auto !important;
    border: 1px solid var(--border) !important;
    background: var(--surface) !important;
    color: var(--item-color) !important;
}
.stButton > button:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

/* Edit button — small yellow circle.
   Targeted by Streamlit's st-key-<key> container class: a wrapper <div> emitted
   through st.markdown renders in its own container and never encloses the
   widget that follows it, so the old .btn-edit descendant selector never matched. */
[class*="st-key-edit_btn_"] button {
    width: 24px !important;
    height: 24px !important;
    min-height: 24px !important;
    padding: 0 !important;
    border-radius: 50% !important;
    background: var(--accent-yellow) !important;
    border: none !important;
    color: transparent !important;
    font-size: 0 !important;
}
[class*="st-key-edit_btn_"] button:hover {
    background: #FFC200 !important;
    border: none !important;
}

/* Delete button — small grey circle, red on hover */
[class*="st-key-del_"] button {
    width: 24px !important;
    height: 24px !important;
    min-height: 24px !important;
    padding: 0 !important;
    border-radius: 50% !important;
    background: var(--border) !important;
    border: none !important;
    color: var(--muted-color) !important;
    font-size: calc(13px * var(--fs-scale)) !important;
    line-height: 1 !important;
}
[class*="st-key-del_"] button:hover {
    background: #FF3B30 !important;
    border: none !important;
    color: white !important;
}

/* Radio horizontal alignment */
.stRadio > div { flex-direction: row !important; gap: 12px; }
.stRadio label { margin-right: 0 !important; }

/* Text input */
.stTextInput > div > div > input {
    font-size: calc(14px * var(--fs-chrome)) !important;
    border-radius: 8px !important;
    background: var(--surface-2) !important;
    color: var(--item-color) !important;
    border: 1px solid var(--border) !important;
}

/* Checkboxes */
.stCheckbox { margin-bottom: 0 !important; }

/* A wrapped "In progress" would break one letter per line in its column. */
[data-testid="stCheckbox"] label { white-space: nowrap; }

/* Checkboxes base size */
input[type="checkbox"] { width: 16px !important; height: 16px !important; }

/* Green "Done" ticks. Two earlier attempts missed for different reasons: a
   <script> inside st.markdown (Streamlit inserts it but never runs it), and
   accent-color (Streamlit hides the native input and paints its own box beside
   it, so the property has nothing to colour). The checked box is that sibling
   <div>. "In progress" deliberately keeps the theme colour. */
[class*="st-key-done_"] label:has(input:checked) > span + div {
    background-color: var(--accent-green) !important;
    border-color: var(--accent-green) !important;
}

/* Expander styling */
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    margin-bottom: 8px !important;
    background: var(--surface) !important;
}
[data-testid="stExpander"] details,
[data-testid="stExpander"] summary { background: var(--surface) !important; }
[data-testid="stExpander"] summary {
    font-size: calc(16px * var(--fs-scale)) !important;
    font-weight: 600 !important;
    color: var(--item-color) !important;
    padding: 10px 14px !important;
}
.my-expander [data-testid="stExpander"] summary {
    color: var(--accent) !important;
}

/* Widget labels (checkboxes, radio, the "You are:" caption) follow the theme. */
[data-testid="stCheckbox"] label, .stRadio label, .stRadio > label,
[data-testid="stWidgetLabel"], [data-testid="stCaptionContainer"] {
    color: var(--item-color) !important;
}
/* Unchecked checkbox: Streamlit paints a white box, invisible on a dark card.
   Scoped to :not(:has(input:checked)) — without that this also repainted the
   CHECKED boxes, wiping out the green Done tick and the In-progress colour. */
:root[data-theme="dark"] [data-testid="stCheckbox"] label:not(:has(input:checked)) > span + div {
    background-color: var(--surface-2) !important;
    border-color: var(--muted-color) !important;
}

/* Text input: the visible fill and border belong to the wrapper div around the
   <input>, not the input itself, so theming the input alone leaves a bright box
   on a dark page. Matched by shape rather than by Streamlit's generated class,
   which changes between releases. */
:root[data-theme="dark"] .stTextInput div:has(> input),
:root[data-theme="dark"] [data-baseweb="input"],
:root[data-theme="dark"] [data-baseweb="base-input"] {
    background-color: var(--surface-2) !important;
    border-color: var(--border) !important;
}
:root[data-theme="dark"] .stTextInput input::placeholder {
    color: var(--muted-color) !important;
    opacity: 1;
}
:root[data-theme="dark"] hr { border-color: var(--border) !important; }

/* Responsive */
@media (max-width: 768px) {
    .block-container { padding-left: 0.5rem; padding-right: 0.5rem; }
}

/* ── Text-size control ────────────────────────────────────────────────────
   Saved to the Home Screen, this runs as a standalone web app with no browser
   chrome, so there is no Safari text-size control to reach for. This is that
   control, living in the page. Its own sizes are deliberately fixed px and not
   scaled, so it stays a constant, findable size at every zoom level. */
#rmg-fs-bar {
    position: fixed;
    /* Bottom LEFT on purpose. Streamlit Cloud pins its own "Manage app" toolbar
       to the bottom right, and the two overlapped there. */
    left: calc(12px + env(safe-area-inset-left, 0px));
    bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    z-index: 9999;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 4px;
    background: var(--pill-bg);
    border: 1px solid var(--border);
    border-radius: 999px;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.10);
    -webkit-backdrop-filter: saturate(180%) blur(8px);
    backdrop-filter: saturate(180%) blur(8px);
}
#rmg-fs-bar button {
    width: 44px;              /* Apple's minimum comfortable touch target */
    height: 44px;
    min-width: 44px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--accent);
    font-family: var(--font-stack);
    font-size: 17px;
    font-weight: 600;
    line-height: 1;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
}
#rmg-fs-bar button:active { background: var(--border); }
#rmg-fs-bar button:disabled { color: #C7C7CC; }
#rmg-fs-sep {
    width: 1px;
    height: 26px;
    margin: 0 2px;
    background: var(--border);
}
#rmg-fs-legible { font-size: 15px !important; }
#rmg-fs-legible[aria-pressed="true"],
#rmg-fs-theme[aria-pressed="true"] {
    background: var(--accent);
    color: #FFFFFF;
}
#rmg-fs-theme { font-size: 17px !important; }
#rmg-fs-value {
    min-width: 46px;
    text-align: center;
    font-family: var(--font-stack);
    font-size: 13px;
    color: var(--muted-color);
    font-variant-numeric: tabular-nums;
}
@media print { #rmg-fs-bar { display: none; } }

/* The control ships inside a components iframe (the only place Streamlit will
   actually run a script). Collapse its slot rather than hiding it, so the
   iframe still loads and executes. */
[class*="st-key-fs_control"] {
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
    margin: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Text size ─────────────────────────────────────────────────────────────────
# Rendered right after the stylesheet so the control is present on every screen,
# including the error page that st.stop()s before any data is drawn.
#
# This is deliberately pure client-side. A Streamlit widget would round-trip to
# the server and rerun the page on every tap, and its value would reset whenever
# iPadOS evicted the session — a Home Screen app relaunches from a fixed URL, so
# there is no query string to carry state either. localStorage is scoped to the
# installed web app and survives relaunch, so the preference sticks.
_FS_CONTROL = """
<script>
(function () {
    var W = window.parent, D = W.document;
    var KEY = 'rmg-font-scale';
    var LEG_KEY = 'rmg-legible';
    var THEME_KEY = 'rmg-theme';
    var STEPS = [0.85, 1, 1.15, 1.3, 1.5, 1.7];

    function read() {
        try {
            var v = parseFloat(W.localStorage.getItem(KEY));
            return STEPS.indexOf(v) >= 0 ? v : 1;
        } catch (e) { return 1; }   // private browsing / storage blocked
    }
    function save(v) { try { W.localStorage.setItem(KEY, String(v)); } catch (e) {} }

    function readLegible() {
        try { return W.localStorage.getItem(LEG_KEY) === '1'; } catch (e) { return false; }
    }
    function saveLegible(on) {
        try { W.localStorage.setItem(LEG_KEY, on ? '1' : '0'); } catch (e) {}
    }

    function readDark() {
        try { return W.localStorage.getItem(THEME_KEY) === 'dark'; } catch (e) { return false; }
    }
    function saveDark(on) {
        try { W.localStorage.setItem(THEME_KEY, on ? 'dark' : 'light'); } catch (e) {}
    }

    var scale = read();
    var legible = readLegible();
    var dark = readDark();

    function apply() {
        D.documentElement.style.setProperty('--fs-scale', String(scale));
        if (legible) {
            D.documentElement.setAttribute('data-legible', '1');
        } else {
            D.documentElement.removeAttribute('data-legible');
        }
        if (dark) {
            D.documentElement.setAttribute('data-theme', 'dark');
        } else {
            D.documentElement.removeAttribute('data-theme');
        }
        var i = STEPS.indexOf(scale);
        var out = D.getElementById('rmg-fs-value');
        var minus = D.getElementById('rmg-fs-minus');
        var plus = D.getElementById('rmg-fs-plus');
        if (out) out.textContent = Math.round(scale * 100) + '%';
        if (minus) minus.disabled = (i <= 0);
        if (plus) plus.disabled = (i >= STEPS.length - 1);
        var leg = D.getElementById('rmg-fs-legible');
        var thm = D.getElementById('rmg-fs-theme');
        if (thm) {
            thm.setAttribute('aria-pressed', dark ? 'true' : 'false');
            thm.textContent = dark ? '\u2600' : '\u263E';
        }
        if (leg) leg.setAttribute('aria-pressed', legible ? 'true' : 'false');
    }

    function toggleLegible() {
        legible = !legible;
        saveLegible(legible);
        apply();
    }

    function toggleDark() {
        dark = !dark;
        saveDark(dark);
        apply();
    }

    function step(dir) {
        var i = STEPS.indexOf(scale);
        if (i < 0) i = STEPS.indexOf(1);
        i = Math.max(0, Math.min(STEPS.length - 1, i + dir));
        scale = STEPS[i];
        save(scale);
        apply();
    }

    function build() {
        if (D.getElementById('rmg-fs-bar')) { apply(); return; }
        var bar = D.createElement('div');
        bar.id = 'rmg-fs-bar';
        bar.setAttribute('role', 'group');
        bar.setAttribute('aria-label', 'Text size');
        bar.innerHTML =
            '<button id="rmg-fs-minus" type="button" aria-label="Smaller text">A\u2212</button>' +
            '<span id="rmg-fs-value" aria-live="polite">100%</span>' +
            '<button id="rmg-fs-plus" type="button" aria-label="Larger text">A+</button>' +
            '<span id="rmg-fs-sep"></span>' +
            '<button id="rmg-fs-legible" type="button" aria-pressed="false" ' +
            'aria-label="High contrast text" title="Darker, heavier text">Aa</button>' +
            '<button id="rmg-fs-theme" type="button" aria-pressed="false" ' +
            'aria-label="Dark mode" title="Dark mode">\u263E</button>';
        D.body.appendChild(bar);
        D.getElementById('rmg-fs-minus').addEventListener('click', function () { step(-1); });
        D.getElementById('rmg-fs-plus').addEventListener('click', function () { step(1); });
        D.getElementById('rmg-fs-legible').addEventListener('click', toggleLegible);
        D.getElementById('rmg-fs-theme').addEventListener('click', toggleDark);
        apply();
    }

    // Appending to <body> puts the bar outside Streamlit's React root, so reruns
    // leave it alone; the observer only matters if the body is ever replaced.
    build();
    new W.MutationObserver(build).observe(D.body, { childList: true });
})();
</script>
"""

with st.container(key="fs_control"):
    components.html(_FS_CONTROL, height=0)


# ── Constants ─────────────────────────────────────────────────────────────────
TEAM        = ["Vesna", "Craig", "Damir"]
RMG_PERSON  = "rMG"
SCOPES      = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME  = "rMG Weekly Tracker"
# ── Google Sheets ─────────────────────────────────────────────────────────────
@st.cache_resource
def _get_worksheet():
    try:
        creds_info = dict(st.secrets["GOOGLE"])
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        client = gspread.authorize(creds)

        def _open():
            ws = client.open(SHEET_NAME).sheet1
            existing = ws.row_values(1)
            if existing != COLS:
                ws.insert_row(COLS, 1)
            return ws

        return retry(_open), None
    except KeyError:
        return None, "setup"
    except Exception as e:
        return None, str(e)


def get_sheet():
    ws, err = _get_worksheet()
    # _get_worksheet returns its error instead of raising, and @st.cache_resource
    # has no TTL — so without this a single 503 during the handshake would be
    # cached for the life of the server process and every later rerun would keep
    # replaying it. Drop the cached failure so the next rerun genuinely retries.
    if err and err != "setup":
        _get_worksheet.clear()
    return ws, err


@st.cache_data(ttl=60)
def load_data(_cache_key: str):
    try:
        ws, err = get_sheet()
        if err:
            return pd.DataFrame(columns=COLS), err
        rows = retry(ws.get_all_records)
        if not rows:
            return pd.DataFrame(columns=COLS), None
        df = pd.DataFrame(rows)
        for col in COLS:
            if col not in df.columns:
                df[col] = ""
        return df[COLS], None
    except Exception as e:
        return pd.DataFrame(columns=COLS), str(e)


def invalidate_cache():
    load_data.clear()


def append_row(ws, row_dict: dict):
    values = [row_dict.get(c, "") for c in COLS]
    retry(lambda: ws.append_row(values, value_input_option="USER_ENTERED"))


def update_row(ws, row_id: str, field: str, value: str):
    cell = retry(lambda: ws.find(str(row_id), in_column=1))
    if cell:
        retry(lambda: ws.update_cell(cell.row, COLS.index(field) + 1, value))
        retry(lambda: ws.update_cell(cell.row, COLS.index("updated_at") + 1, date.today().isoformat()))


def delete_row(ws, row_id: str):
    cell = retry(lambda: ws.find(str(row_id), in_column=1))
    if cell:
        retry(lambda: ws.delete_rows(cell.row))


# ── Session state ─────────────────────────────────────────────────────────────
if "active_user" not in st.session_state:
    st.session_state["active_user"] = "Damir"
if "current_week" not in st.session_state:
    st.session_state["current_week"] = get_monday(date.today())
for _p in TEAM + [RMG_PERSON]:
    if f"input_n_{_p}" not in st.session_state:
        st.session_state[f"input_n_{_p}"] = 0

# ── Rollover and chat-add helpers ────────────────────────────────────────────
def _do_rollover(current_week, current_week_str, force=False):
    """Carry over un-done items from previous week to current. Idempotent."""
    ws, err = get_sheet()
    if err:
        st.error(f"Sheet error: {err}")
        return 0, 0
    last_week_str = (current_week - timedelta(weeks=1)).isoformat()
    invalidate_cache()
    df_all, _ = load_data("rollover")
    to_carry, skipped = plan_rollover(df_all, last_week_str, current_week_str)
    for row in to_carry:
        append_row(ws, {
            "id": str(uuid.uuid4())[:8],
            "person": row["person"],
            "week_start": current_week_str,
            "type": "item",
            "item": row["item"],
            "status": row["status"],
            "created_at": date.today().isoformat(),
            "updated_at": date.today().isoformat(),
        })
    carried = len(to_carry)
    invalidate_cache()
    if force:
        if carried == 0 and skipped == 0:
            st.info("Nothing to carry over.")
        else:
            msg = f"Carried over {carried} item{'s' if carried != 1 else ''}."
            if skipped > 0:
                msg += f" Skipped {skipped} already present."
            st.success(msg)
    return carried, skipped


def _auto_rollover_if_needed(current_week, current_week_str):
    """Auto-carry on first load of a new week if current week is empty and last week has items."""
    if get_monday(date.today()) != current_week:
        return
    flag = f"_auto_ro_{current_week_str}"
    if st.session_state.get(flag, False):
        return
    df_check, check_err = load_data("auto_check")
    if check_err:
        # Sheet unreachable — leave the flag unset so this runs once it recovers,
        # rather than recording a rollover that never happened.
        return
    if df_check.empty:
        st.session_state[flag] = True
        return
    if (df_check["week_start"] == current_week_str).any():
        st.session_state[flag] = True
        return
    last_week_str = (current_week - timedelta(weeks=1)).isoformat()
    if not (df_check["week_start"] == last_week_str).any():
        st.session_state[flag] = True
        return
    try:
        carried, _ = _do_rollover(current_week, current_week_str, force=False)
        if carried > 0:
            st.toast(f"Auto-carried {carried} items from last week.", icon="🔄")
    except Exception:
        pass
    st.session_state[flag] = True


def _handle_chat_add():
    """If URL has ?add_to=X&item=Y&token=Z and token matches secret, append item to current week."""
    qp = st.query_params
    if not all(k in qp for k in ("add_to", "item", "token")):
        return
    try:
        expected = st.secrets.get("CHAT_ADD_TOKEN", "")
    except Exception:
        expected = ""
    if not expected or qp.get("token") != expected:
        st.query_params.clear()
        return
    add_to = qp.get("add_to", "")
    item_text = qp.get("item", "").strip()
    if not item_text or add_to not in (TEAM + [RMG_PERSON]):
        st.query_params.clear()
        return
    ws, err = get_sheet()
    if err:
        st.query_params.clear()
        return
    week_start = get_monday(date.today()).isoformat()
    df_check, _ = load_data("chat_add")
    week_existing = df_check[df_check["week_start"] == week_start] if not df_check.empty else pd.DataFrame(columns=COLS)
    already = any(
        (r["person"] == add_to and str(r["item"]).strip().lower() == item_text.lower())
        for _, r in week_existing.iterrows()
    )
    if not already:
        append_row(ws, {
            "id": str(uuid.uuid4())[:8],
            "person": add_to,
            "week_start": week_start,
            "type": "item",
            "item": item_text,
            "status": "pending",
            "created_at": date.today().isoformat(),
            "updated_at": date.today().isoformat(),
        })
        invalidate_cache()
        st.toast(f"Added to {add_to}: {item_text}", icon="✅")
    else:
        st.toast("Already in this week — not added.", icon="ℹ️")
    st.query_params.clear()


current_week     = st.session_state["current_week"]
current_week_str = current_week.isoformat()
is_current_week  = (current_week == get_monday(date.today()))

# Run pre-render handlers (URL-driven chat-add + auto-rollover)
_handle_chat_add()
_auto_rollover_if_needed(current_week, current_week_str)


# ── TOP BAR ───────────────────────────────────────────────────────────────────
c_user, c_week, c_roll = st.columns([4, 3, 2])

with c_user:
    active_user = st.radio(
        "You are:",
        TEAM,
        index=TEAM.index(st.session_state["active_user"]),
        horizontal=True,
    )
    st.session_state["active_user"] = active_user

with c_week:
    wc1, wc2, wc3 = st.columns([1, 5, 1])
    with wc1:
        if st.button("←"):
            st.session_state["current_week"] -= timedelta(weeks=1)
            invalidate_cache()
            st.rerun()
    with wc2:
        st.markdown(f"<div style='text-align:center;font-size:calc(14px * var(--fs-chrome));padding-top:6px;'>{format_week(current_week)}</div>", unsafe_allow_html=True)
    with wc3:
        if st.button("→"):
            st.session_state["current_week"] += timedelta(weeks=1)
            invalidate_cache()
            st.rerun()

with c_roll:
    rolling = st.session_state.get("rolling_over", False)
    if st.button("Weekly Rollover", use_container_width=True, disabled=rolling):
        st.session_state["rolling_over"] = True
        with st.spinner("Running rollover…"):
            try:
                _do_rollover(current_week, current_week_str, force=True)
            except Exception as e:
                st.error(str(e))
            finally:
                st.session_state["rolling_over"] = False

if not is_current_week:
    st.caption("Viewing a past week — read only.")

st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────────────────
df, load_err = load_data(current_week_str)

if load_err == "setup":
    st.warning("Google Sheets not configured. Add secrets in Streamlit Cloud settings.")
    st.stop()
elif load_err:
    # Never leave a failure sitting in the data cache for the rest of its TTL.
    load_data.clear()
    if is_transient(load_err):
        st.error("Google Sheets is temporarily unavailable. This is usually brief — retry in a moment.")
        st.caption(str(load_err))
    else:
        st.error(f"Could not load data: {load_err}")
    if st.button("Retry"):
        _get_worksheet.clear()
        st.rerun()
    st.stop()

week_df = df[df["week_start"] == current_week_str].copy() if not df.empty else pd.DataFrame(columns=COLS)


# ── Item renderer ─────────────────────────────────────────────────────────────
def render_items(items_df, can_edit, add_key):
    """Render a list of items with numbering, status checkboxes, edit and delete."""
    items_df = sort_items(items_df)

    for i, (_, row) in enumerate(items_df.iterrows(), 1):
        item_id  = row["id"]
        status   = row.get("status", "pending")
        # Widget keys must be unique even if two sheet rows share the same id —
        # section name + position guarantees that; item_id kept for readability.
        # The status is part of the key too: Streamlit ignores the `value=` argument
        # once a key exists in session_state, so a key that outlives a status change
        # would keep showing the pre-change checkbox state.
        rk       = f"{add_key}_{i}_{item_id}_{status}"
        is_done  = (status == "done")
        is_prog  = (status == "in_progress")
        editing  = st.session_state.get(f"edit_{rk}", False)

        if editing and can_edit:
            c_n, c_txt, c_done, c_prog, c_save, c_cancel = st.columns([0.35, 5.9, 1.15, 1.8, 0.75, 0.85])
            with c_n:
                st.markdown(f'<div style="padding-top:8px;color:var(--muted-color);font-weight:var(--muted-weight);font-size:calc(14px * var(--fs-scale));">{i}.</div>', unsafe_allow_html=True)
            with c_txt:
                edited_text = st.text_input("edit", value=row["item"], key=f"edit_val_{rk}", label_visibility="collapsed")
            with c_done:
                st.checkbox("Done", value=is_done, key=f"done_{rk}", disabled=True)
            with c_prog:
                st.checkbox("In progress", value=is_prog, key=f"prog_{rk}", disabled=True)
            with c_save:
                if st.button("Save", key=f"save_{rk}", use_container_width=True):
                    try:
                        ws, err = get_sheet()
                        if not err and edited_text:
                            update_row(ws, item_id, "item", edited_text)
                            invalidate_cache()
                        st.session_state[f"edit_{rk}"] = False
                        st.session_state.pop(f"edit_val_{rk}", None)
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c_cancel:
                if st.button("Cancel", key=f"cancel_{rk}", use_container_width=True):
                    st.session_state[f"edit_{rk}"] = False
                    st.session_state.pop(f"edit_val_{rk}", None)
                    st.rerun()

        else:
            # Text style by status. The in-progress accent sits on the text cell
            # itself: the old .item-inprog wrapper was emitted as its own
            # st.markdown element, so it never enclosed the columns below it.
            txt_style = ("padding-top:6px; font-size:calc(15px * var(--fs-scale));"
                         " line-height:var(--line-height);"
                         " letter-spacing:var(--tracking);")
            if is_done:
                txt_style += " color:var(--muted-color); font-weight:var(--muted-weight);"
            elif is_prog:
                txt_style += (" color:var(--item-color); font-weight:var(--item-weight);"
                              " border-left:3px solid var(--accent-orange); padding-left:8px;")
            else:
                txt_style += " color:var(--item-color); font-weight:var(--item-weight);"

            c_n, c_txt, c_done, c_prog, c_edit, c_del = st.columns([0.35, 5.9, 1.15, 1.8, 0.75, 0.55])
            with c_n:
                st.markdown(f'<div style="padding-top:8px;color:var(--muted-color);font-weight:var(--muted-weight);font-size:calc(14px * var(--fs-scale));">{i}.</div>', unsafe_allow_html=True)
            with c_txt:
                st.markdown(f'<div style="{txt_style}">{linkify(row["item"])}</div>', unsafe_allow_html=True)
            with c_done:
                new_done = st.checkbox("Done", value=is_done, key=f"done_{rk}", disabled=not is_current_week)
            with c_prog:
                new_prog = st.checkbox("In progress", value=is_prog, key=f"prog_{rk}", disabled=not is_current_week)

            with c_edit:
                if can_edit and st.button("●", key=f"edit_btn_{rk}", use_container_width=True):
                    st.session_state[f"edit_{rk}"] = True
                    st.rerun()
            with c_del:
                if can_edit and st.button("×", key=f"del_{rk}", use_container_width=True):
                    try:
                        ws, err = get_sheet()
                        if not err:
                            delete_row(ws, item_id)
                            invalidate_cache()
                            st.rerun()
                    except Exception as e:
                        st.error(str(e))

            # Status update
            if is_current_week:
                new_status = next_status(status, new_done, new_prog)
                if new_status != status:
                    try:
                        ws, err = get_sheet()
                        if not err:
                            update_row(ws, item_id, "status", new_status)
                            invalidate_cache()
                            st.rerun()
                    except Exception as e:
                        st.error(str(e))

    # Add input
    if can_edit and is_current_week:
        n = st.session_state[f"input_n_{add_key}"]
        new_item = st.text_input(
            "add",
            placeholder="+ Add item…",
            label_visibility="collapsed",
            key=f"new_{add_key}_{n}",
        )
        if new_item:
            try:
                ws, err = get_sheet()
                if err:
                    st.error(f"Sheet error: {err}")
                else:
                    person_label = add_key
                    already = any(
                        str(r["item"]).strip().lower() == new_item.strip().lower()
                        for _, r in items_df.iterrows()
                    )
                    if already:
                        st.warning("Already on the list.")
                    else:
                        append_row(ws, {
                            "id": str(uuid.uuid4())[:8],
                            "person": person_label,
                            "week_start": current_week_str,
                            "type": "item",
                            "item": new_item,
                            "status": "pending",
                            "created_at": date.today().isoformat(),
                            "updated_at": date.today().isoformat(),
                        })
                        invalidate_cache()
                        st.session_state[f"input_n_{add_key}"] += 1
                        st.rerun()
            except Exception as e:
                st.error(str(e))


# ── Person sections ───────────────────────────────────────────────────────────
for person in TEAM:   # Vesna, Craig, Damir
    is_me = (person == active_user)
    if is_me:
        st.markdown('<div class="my-expander">', unsafe_allow_html=True)
    with st.expander(person, expanded=True):
        person_items = week_df[week_df["person"] == person] if not week_df.empty else pd.DataFrame(columns=COLS)
        render_items(person_items, can_edit=(is_me and is_current_week), add_key=person)
    if is_me:
        st.markdown('</div>', unsafe_allow_html=True)

# ── rMG section ───────────────────────────────────────────────────────────────
with st.expander("rMG", expanded=True):
    rmg_items = week_df[week_df["person"] == RMG_PERSON] if not week_df.empty else pd.DataFrame(columns=COLS)
    render_items(rmg_items, can_edit=is_current_week, add_key=RMG_PERSON)
