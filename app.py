import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date, timedelta
import uuid

st.set_page_config(page_title="rMG Weekly", layout="wide", page_icon="📋")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    background-color: #F2F2F7 !important;
    font-size: 15px !important;
}
#MainMenu, header, footer { visibility: hidden; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 860px; }

/* Top bar */
.top-bar {
    display: flex;
    align-items: center;
    gap: 24px;
    background: white;
    border-radius: 10px;
    border: 1px solid #E5E5EA;
    padding: 10px 16px;
    margin-bottom: 18px;
    flex-wrap: wrap;
}

/* Person section */
.person-header {
    font-size: 17px;
    font-weight: 600;
    color: #1C1C1E;
    padding: 6px 0 2px 0;
    border-bottom: 2px solid #007AFF;
    margin-bottom: 8px;
    margin-top: 16px;
}
.person-header-mine {
    font-size: 17px;
    font-weight: 600;
    color: #007AFF;
    padding: 6px 0 2px 0;
    border-bottom: 2px solid #007AFF;
    margin-bottom: 8px;
    margin-top: 16px;
}

/* Item rows */
.item-row {
    display: flex;
    align-items: center;
    background: white;
    border-radius: 8px;
    border: 1px solid #E5E5EA;
    padding: 8px 12px;
    margin-bottom: 4px;
    font-size: 15px;
}
.item-done {
    text-decoration: line-through;
    color: #8E8E93;
}

/* Buttons */
.stButton > button {
    border-radius: 7px !important;
    font-size: 14px !important;
    padding: 4px 12px !important;
    height: auto !important;
    border: 1px solid #E5E5EA !important;
    background: white !important;
    color: #3C3C43 !important;
}
.stButton > button:hover {
    border-color: #007AFF !important;
    color: #007AFF !important;
}

/* Radio horizontal alignment */
.stRadio > div { flex-direction: row !important; gap: 12px; }
.stRadio label { margin-right: 0 !important; }

/* Text input */
.stTextInput > div > div > input {
    font-size: 14px !important;
    border-radius: 8px !important;
    background: #F9F9FB !important;
}

/* Checkboxes */
.stCheckbox { margin-bottom: 0 !important; }

/* Responsive */
@media (max-width: 768px) {
    .block-container { padding-left: 0.5rem; padding-right: 0.5rem; }
}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
TEAM        = ["Vesna", "Craig", "Damir"]
SCOPES      = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME  = "rMG Weekly Tracker"
COLS        = ["id", "person", "week_start", "type", "item", "status", "created_at", "updated_at"]


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def format_week(monday: date) -> str:
    end = monday + timedelta(days=6)
    return f"{monday.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"


# ── Google Sheets ─────────────────────────────────────────────────────────────
@st.cache_resource
def _get_worksheet():
    try:
        creds_info = dict(st.secrets["GOOGLE"])
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        ws = client.open(SHEET_NAME).sheet1
        existing = ws.row_values(1)
        if existing != COLS:
            ws.insert_row(COLS, 1)
        return ws, None
    except KeyError:
        return None, "setup"
    except Exception as e:
        return None, str(e)


def get_sheet():
    return _get_worksheet()


@st.cache_data(ttl=60)
def load_data(_cache_key: str):
    try:
        ws, err = get_sheet()
        if err:
            return pd.DataFrame(columns=COLS), err
        rows = ws.get_all_records()
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
    ws.append_row([row_dict.get(c, "") for c in COLS], value_input_option="USER_ENTERED")


def update_row(ws, row_id: str, field: str, value: str):
    cell = ws.find(row_id, in_column=1)
    if cell:
        ws.update_cell(cell.row, COLS.index(field) + 1, value)
        ws.update_cell(cell.row, COLS.index("updated_at") + 1, date.today().isoformat())


# ── Session state ─────────────────────────────────────────────────────────────
if "active_user" not in st.session_state:
    st.session_state["active_user"] = "Damir"
if "current_week" not in st.session_state:
    st.session_state["current_week"] = get_monday(date.today())

current_week     = st.session_state["current_week"]
current_week_str = current_week.isoformat()
is_current_week  = (current_week == get_monday(date.today()))


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
        st.markdown(f"<div style='text-align:center;font-size:14px;padding-top:6px;'>{format_week(current_week)}</div>", unsafe_allow_html=True)
    with wc3:
        if st.button("→"):
            st.session_state["current_week"] += timedelta(weeks=1)
            invalidate_cache()
            st.rerun()

with c_roll:
    if st.button("Weekly Rollover", use_container_width=True):
        with st.spinner("Running rollover…"):
            try:
                ws, err = get_sheet()
                if err:
                    st.error(f"Sheet error: {err}")
                else:
                    last_week_str = (current_week - timedelta(weeks=1)).isoformat()
                    df_all, _ = load_data("rollover")
                    carried = 0
                    for _, row in df_all[df_all["week_start"] == last_week_str].iterrows():
                        if row["status"] != "done":
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
                            carried += 1
                    invalidate_cache()
                    st.success(f"Carried over {carried} items.")
            except Exception as e:
                st.error(str(e))

if not is_current_week:
    st.caption("Viewing a past week — read only.")

st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────────────────
df, load_err = load_data(current_week_str)

if load_err == "setup":
    st.warning("Google Sheets not configured. Add secrets in Streamlit Cloud settings.")
    st.stop()
elif load_err:
    st.error(f"Could not load data: {load_err}")
    st.stop()

week_df = df[df["week_start"] == current_week_str].copy() if not df.empty else pd.DataFrame(columns=COLS)


# ── Person sections ───────────────────────────────────────────────────────────
for person in TEAM:   # Vesna, Craig, Damir
    is_me = (person == active_user)
    header_class = "person-header-mine" if is_me else "person-header"
    st.markdown(f'<div class="{header_class}">{person}</div>', unsafe_allow_html=True)

    person_items = week_df[week_df["person"] == person] if not week_df.empty else pd.DataFrame(columns=COLS)

    for _, row in person_items.iterrows():
        item_id   = row["id"]
        status    = row.get("status", "pending")
        is_done   = (status == "done")
        is_prog   = (status == "in_progress")
        text_style = "text-decoration:line-through;color:#8E8E93;" if is_done else ""

        col_text, col_done, col_prog = st.columns([7, 1.2, 1.8])

        with col_text:
            st.markdown(f'<div style="{text_style}padding-top:6px;">{row["item"]}</div>', unsafe_allow_html=True)

        with col_done:
            new_done = st.checkbox("Done", value=is_done, key=f"done_{item_id}", disabled=not is_current_week)

        with col_prog:
            new_prog = st.checkbox("In progress", value=is_prog, key=f"prog_{item_id}", disabled=not is_current_week)

        # Resolve status from checkboxes
        if is_current_week:
            if new_done and not is_done:
                new_status = "done"
            elif new_prog and not is_prog and not new_done:
                new_status = "in_progress"
            elif not new_done and not new_prog and status in ("done", "in_progress"):
                new_status = "pending"
            else:
                new_status = status

            if new_status != status:
                try:
                    ws, err = get_sheet()
                    if not err:
                        update_row(ws, item_id, "status", new_status)
                        invalidate_cache()
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

    # Add item input — only for your own section, current week
    if is_me and is_current_week:
        new_item = st.text_input(
            "add",
            placeholder="+ Add item…",
            label_visibility="collapsed",
            key=f"new_{person}",
        )
        if new_item:
            try:
                ws, err = get_sheet()
                if err:
                    st.error(f"Sheet error: {err}")
                else:
                    append_row(ws, {
                        "id": str(uuid.uuid4())[:8],
                        "person": person,
                        "week_start": current_week_str,
                        "type": "item",
                        "item": new_item,
                        "status": "pending",
                        "created_at": date.today().isoformat(),
                        "updated_at": date.today().isoformat(),
                    })
                    invalidate_cache()
                    st.session_state[f"new_{person}"] = ""
                    st.rerun()
            except Exception as e:
                st.error(str(e))
