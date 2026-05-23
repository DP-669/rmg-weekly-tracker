import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date, timedelta
import uuid

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="rMG Weekly", layout="wide", page_icon="📋")

# ── Google Fonts + global CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif !important;
    background-color: #F2F2F7 !important;
}
#MainMenu, header, footer { visibility: hidden; }
.block-container { padding-top: 1.5rem; }

/* Cards */
.task-card {
    background: white;
    border-radius: 12px;
    border: 1px solid #E8E8E8;
    padding: 12px 14px;
    margin-bottom: 8px;
}
.task-card-active {
    background: #F0F7FF;
    border-radius: 12px;
    border: 1px solid #C7E0FF;
    padding: 12px 14px;
    margin-bottom: 8px;
}
/* Section headers */
.section-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #8E8E93;
    margin: 14px 0 6px 0;
}

/* Status buttons */
.stButton > button {
    border-radius: 8px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 12px !important;
    padding: 4px 10px !important;
    height: auto !important;
    min-height: 28px !important;
    border: 1px solid #E8E8E8 !important;
    background: white !important;
    color: #3C3C43 !important;
}
.stButton > button:hover {
    border-color: #007AFF !important;
    color: #007AFF !important;
}

/* Column header */
.col-header {
    font-size: 16px;
    font-weight: 600;
    color: #1C1C1E;
    padding: 8px 0 4px 0;
    border-bottom: 2px solid #007AFF;
    margin-bottom: 12px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
TEAM = ["Damir", "Vesna", "Craig"]
STATUSES = ["pending", "in_progress", "done", "blocked"]
STATUS_LABELS = {"pending": "Pending", "in_progress": "In Progress", "done": "Done", "blocked": "Blocked"}
STATUS_COLORS = {"pending": "#8E8E93", "in_progress": "#007AFF", "done": "#34C759", "blocked": "#FF3B30"}
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "rMG Weekly Tracker"
COLS = ["id", "person", "week_start", "type", "item", "status", "created_at", "updated_at"]


def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def format_week(monday: date) -> str:
    end = monday + timedelta(days=6)
    return f"{monday.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"


# ── Google Sheets connection ───────────────────────────────────────────────────
@st.cache_resource
def _get_worksheet():
    """Create and cache the gspread worksheet object for the whole session."""
    try:
        creds_info = dict(st.secrets["GOOGLE"])
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        client = gspread.authorize(creds)
        sh = client.open(SHEET_NAME)
        ws = sh.sheet1
        # Ensure header row exists — done once at startup, not on every call
        existing = ws.row_values(1)
        if existing != COLS:
            ws.insert_row(COLS, 1)
        return ws, None
    except KeyError:
        return None, "setup"
    except Exception as e:
        return None, str(e)


def get_sheet():
    """Return the cached worksheet. No API calls on repeated invocations."""
    return _get_worksheet()


@st.cache_data(ttl=60)
def load_data(_ws_key: str):
    """Load all rows from sheet. Cache for 60 s; _ws_key busts the cache on writes."""
    try:
        sheet, err = get_sheet()
        if err:
            return pd.DataFrame(columns=COLS), err
        rows = sheet.get_all_records()
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
    """Append a new row to the sheet."""
    row = [row_dict.get(c, "") for c in COLS]
    ws.append_row(row, value_input_option="USER_ENTERED")


def update_row(ws, row_id: str, field: str, value: str):
    """Find row by id and update a field."""
    cell = ws.find(row_id, in_column=1)
    if cell:
        col_idx = COLS.index(field) + 1
        ws.update_cell(cell.row, col_idx, value)
        ts_col = COLS.index("updated_at") + 1
        ws.update_cell(cell.row, ts_col, date.today().isoformat())


def delete_row(ws, row_id: str):
    """Find row by id and delete it."""
    cell = ws.find(row_id, in_column=1)
    if cell:
        ws.delete_rows(cell.row)


# ── Session state init ────────────────────────────────────────────────────────
if "active_user" not in st.session_state:
    st.session_state["active_user"] = "Damir"
if "current_week" not in st.session_state:
    st.session_state["current_week"] = get_monday(date.today())
if "editing_item" not in st.session_state:
    st.session_state["editing_item"] = None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 👤 You are")
    active_user = st.radio(
        "Select user",
        TEAM,
        index=TEAM.index(st.session_state["active_user"]),
        label_visibility="collapsed",
    )
    st.session_state["active_user"] = active_user

    st.markdown("---")
    st.markdown("### 📅 Week")
    col_prev, col_next = st.columns(2)
    with col_prev:
        if st.button("◀ Prev"):
            st.session_state["current_week"] -= timedelta(weeks=1)
            invalidate_cache()
    with col_next:
        if st.button("Next ▶"):
            st.session_state["current_week"] += timedelta(weeks=1)
            invalidate_cache()

    current_week = st.session_state["current_week"]
    is_current_week = (current_week == get_monday(date.today()))
    st.caption(f"{'📍 ' if is_current_week else '🕐 '}Week of {current_week.strftime('%b %d, %Y')}")
    if not is_current_week:
        st.caption("_Past weeks are read-only_")

    st.markdown("---")
    st.markdown("### 🔄 Weekly Rollover")
    if st.button("Run Weekly Rollover", use_container_width=True):
        with st.spinner("Running rollover..."):
            try:
                sheet, err = get_sheet()
                if err:
                    st.error(f"Sheet error: {err}")
                else:
                    last_week = current_week - timedelta(weeks=1)
                    last_week_str = last_week.isoformat()
                    this_week_str = current_week.isoformat()
                    df, _ = load_data("rollover")
                    last_items = df[df["week_start"] == last_week_str]
                    archived = 0
                    carried = 0
                    for _, row in last_items.iterrows():
                        if row["status"] == "done":
                            archived += 1
                        else:
                            new_id = str(uuid.uuid4())[:8]
                            append_row(sheet, {
                                "id": new_id,
                                "person": row["person"],
                                "week_start": this_week_str,
                                "type": row["type"],
                                "item": row["item"],
                                "status": row["status"],
                                "created_at": date.today().isoformat(),
                                "updated_at": date.today().isoformat(),
                            })
                            carried += 1
                    invalidate_cache()
                    st.success(f"✅ Archived {archived} done · Carried over {carried} items")
            except Exception as e:
                st.error(f"Rollover failed: {e}")



# ── Main header ───────────────────────────────────────────────────────────────
st.markdown(f"# 📋 rMG Weekly")
st.markdown(f"**Week of {format_week(st.session_state['current_week'])}**")
st.markdown("---")

# ── Load data ─────────────────────────────────────────────────────────────────
current_week_str = st.session_state["current_week"].isoformat()
df, load_err = load_data(current_week_str)

if load_err == "setup":
    st.warning("⚠️ **Google Sheets not configured yet.**\n\nCreate `.streamlit/secrets.toml` with your service account credentials to connect to the sheet. See README for instructions.", icon="🔧")
    st.stop()
elif load_err:
    st.error(f"Could not load sheet data: {load_err}")
    st.stop()

week_df = df[df["week_start"] == current_week_str].copy() if not df.empty else pd.DataFrame(columns=COLS)
read_only = not is_current_week



# ── Render task item ───────────────────────────────────────────────────────────
def render_task(row, is_active_col: bool, read_only: bool):
    item_id = row["id"]
    card_class = "task-card-active" if is_active_col else "task-card"

    st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)

    # Task text
    if not read_only and st.session_state["editing_item"] == item_id:
        new_text = st.text_area(
            "Edit task",
            value=row["item"],
            key=f"edit_{item_id}",
            label_visibility="collapsed",
            height=80,
        )
        col_save, col_cancel = st.columns(2)
        with col_save:
            if st.button("Save", key=f"save_{item_id}"):
                try:
                    sheet, err = get_sheet()
                    if err:
                        st.error(f"Sheet error: {err}")
                    else:
                        update_row(sheet, item_id, "item", new_text)
                        st.session_state["editing_item"] = None
                        invalidate_cache()
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
        with col_cancel:
            if st.button("Cancel", key=f"cancel_{item_id}"):
                st.session_state["editing_item"] = None
                st.rerun()
    else:
        text_col, edit_col, del_col = st.columns([6, 1, 1])
        with text_col:
            current_status = row.get("status", "pending")
            color = STATUS_COLORS.get(current_status, "#8E8E93")
            st.markdown(
                f'<span style="color:{color};font-size:10px;">●</span> {row["item"]}',
                unsafe_allow_html=True,
            )
        if not read_only:
            with edit_col:
                if st.button("✏️", key=f"edit_btn_{item_id}", help="Edit"):
                    st.session_state["editing_item"] = item_id
                    st.rerun()
            with del_col:
                if st.button("🗑️", key=f"del_{item_id}", help="Delete"):
                    try:
                        sheet, err = get_sheet()
                        if err:
                            st.error(f"Sheet error: {err}")
                        else:
                            delete_row(sheet, item_id)
                            invalidate_cache()
                            st.rerun()
                    except Exception as e:
                        st.error(str(e))

    # Status row
    if not read_only:
        st.markdown('<div style="margin-top:6px;">', unsafe_allow_html=True)
        status_cols = st.columns(4)
        for i, s in enumerate(STATUSES):
            with status_cols[i]:
                current = row.get("status", "pending")
                label = STATUS_LABELS[s]
                is_selected = (current == s)
                btn_style = f"background:#007AFF!important;color:white!important;border-color:#007AFF!important;" if is_selected else ""
                if st.button(
                    label,
                    key=f"status_{item_id}_{s}",
                    help=f"Set {label}",
                    use_container_width=True,
                ):
                    if not is_selected:
                        try:
                            sheet, err = get_sheet()
                            if err:
                                st.error(f"Sheet error: {err}")
                            else:
                                update_row(sheet, item_id, "status", s)
                                invalidate_cache()
                                st.rerun()
                        except Exception as e:
                            st.error(str(e))
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        current_status = row.get("status", "pending")
        st.caption(f"Status: {STATUS_LABELS.get(current_status, current_status)}")

    st.markdown('</div>', unsafe_allow_html=True)



# ── Three-column layout ────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
columns_map = {"Damir": col1, "Vesna": col2, "Craig": col3}

for person, col in columns_map.items():
    is_active_col = (person == st.session_state["active_user"])
    person_df = week_df[week_df["person"] == person] if not week_df.empty else pd.DataFrame(columns=COLS)

    with col:
        header_color = "#007AFF" if is_active_col else "#8E8E93"
        active_badge = " 👤" if is_active_col else ""
        st.markdown(
            f'<div class="col-header" style="border-color:{header_color};">{person}{active_badge}</div>',
            unsafe_allow_html=True,
        )

        # ── Plans section ──────────────────────────────────────────────────────
        st.markdown('<div class="section-label">📌 Plans</div>', unsafe_allow_html=True)
        plans = person_df[person_df["type"] == "plan"] if not person_df.empty else pd.DataFrame(columns=COLS)
        if plans.empty:
            st.caption("_No plans yet_")
        else:
            for _, row in plans.iterrows():
                render_task(row, is_active_col, read_only)

        if not read_only and is_active_col:
            new_plan = st.text_input(
                "add_plan",
                placeholder="+ Add a plan…",
                label_visibility="collapsed",
                key=f"new_plan_{person}",
            )
            if new_plan:
                try:
                    sheet, err = get_sheet()
                    if err:
                        st.error(f"Sheet error: {err}")
                    else:
                        append_row(sheet, {
                            "id": str(uuid.uuid4())[:8],
                            "person": person,
                            "week_start": current_week_str,
                            "type": "plan",
                            "item": new_plan,
                            "status": "pending",
                            "created_at": date.today().isoformat(),
                            "updated_at": date.today().isoformat(),
                        })
                        invalidate_cache()
                        st.rerun()
                except Exception as e:
                    st.error(str(e))

        # ── Accomplishments section ────────────────────────────────────────────
        st.markdown('<div class="section-label">✅ Accomplishments</div>', unsafe_allow_html=True)
        accoms = person_df[person_df["type"] == "accomplishment"] if not person_df.empty else pd.DataFrame(columns=COLS)
        if accoms.empty:
            st.caption("_No accomplishments yet_")
        else:
            for _, row in accoms.iterrows():
                render_task(row, is_active_col, read_only)

        if not read_only and is_active_col:
            new_accom = st.text_input(
                "add_accom",
                placeholder="+ Add an accomplishment…",
                label_visibility="collapsed",
                key=f"new_accom_{person}",
            )
            if new_accom:
                try:
                    sheet, err = get_sheet()
                    if err:
                        st.error(f"Sheet error: {err}")
                    else:
                        append_row(sheet, {
                            "id": str(uuid.uuid4())[:8],
                            "person": person,
                            "week_start": current_week_str,
                            "type": "accomplishment",
                            "item": new_accom,
                            "status": "done",
                            "created_at": date.today().isoformat(),
                            "updated_at": date.today().isoformat(),
                        })
                        invalidate_cache()
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
