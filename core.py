"""Pure logic for the weekly tracker — no Streamlit, no Google Sheets.

Everything here is a plain function over plain data so it can be tested without
a browser or a network call. The bugs this module exists to pin down were all in
logic of exactly this shape: an unstable sort, a status transition that read the
wrong inputs, an error classifier, and the rollover de-duplication.
"""

import hashlib
import html
import re
import time
from datetime import date, timedelta

COLS = ["id", "person", "week_start", "type", "item", "status", "created_at", "updated_at"]

# Display order for a person's list.
STATUS_ORDER = {"in_progress": 0, "pending": 1, "done": 2}

# Google returns these when it is busy or rate-limiting, not when the request is
# wrong. They are worth retrying; nothing else is.
TRANSIENT_CODES = {429, 500, 502, 503, 504}


# ── Weeks ─────────────────────────────────────────────────────────────────────
def get_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def format_week(monday: date) -> str:
    end = monday + timedelta(days=6)
    return f"{monday.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"


# ── Item text ─────────────────────────────────────────────────────────────────
_MD_LINK = re.compile(r'\[([^\]]+)\]\((https?://[^)\s]+)\)')
_BARE_URL = re.compile(r'https?://[^\s<>"\'()]+')
_TRAILING = '.,;:!?'


def _anchor(url: str, label: str) -> str:
    return (f'<a href="{html.escape(url, quote=True)}" target="_blank">'
            f'{html.escape(label)}</a>')


def _linkify_bare(segment: str) -> str:
    out, pos = [], 0
    for m in _BARE_URL.finditer(segment):
        url = m.group(0).rstrip(_TRAILING)
        out.append(html.escape(segment[pos:m.start()]))
        out.append(_anchor(url, url))
        pos = m.start() + len(url)
    out.append(html.escape(segment[pos:]))
    return ''.join(out)


def linkify(text) -> str:
    """Render item text as HTML: [label](url) and bare URLs become links.

    The output goes out through unsafe_allow_html, so every part is escaped for
    the context it lands in — plain text as text, URLs as attribute values.

    Matching happens on the *raw* text, before escaping. Escaping first and then
    matching looks safer but is not: html.escape removes the quote and angle
    bracket that terminate a URL match, so the pattern runs straight past the
    URL and swallows the following entities into the href.
    """
    text = str(text)
    out, pos = [], 0
    for m in _MD_LINK.finditer(text):
        out.append(_linkify_bare(text[pos:m.start()]))
        out.append(_anchor(m.group(2), m.group(1)))
        pos = m.end()
    out.append(_linkify_bare(text[pos:]))
    return ''.join(out)


# ── Status ────────────────────────────────────────────────────────────────────
def next_status(status: str, done_checked: bool, prog_checked: bool) -> str:
    """Resolve a row's new status from its checkboxes.

    Only one checkbox can change per rerun, so this reads the *toggle* rather
    than the combination of both boxes. Reading the combination is what used to
    send an item to in_progress when Done was unticked.
    """
    is_done = (status == "done")
    is_prog = (status == "in_progress")
    if done_checked != is_done:
        return "done" if done_checked else "pending"
    if prog_checked != is_prog:
        return "in_progress" if prog_checked else "pending"
    return status


def sort_items(items_df):
    """Order a person's items in_progress -> pending -> done.

    The sort is stable so items sharing a status keep their sheet order; pandas'
    default quicksort is not, and re-permuted the list on every rerun.
    """
    if items_df.empty:
        return items_df
    out = items_df.copy()
    out["_s"] = out["status"].map(lambda s: STATUS_ORDER.get(s, 1))
    return out.sort_values("_s", kind="stable").drop(columns=["_s"])


# ── Transient Google API failures ─────────────────────────────────────────────
def is_transient(err) -> bool:
    """True for a retryable Google API failure. Accepts an exception or a string."""
    resp = getattr(err, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        code = getattr(err, "code", None)
    if code in TRANSIENT_CODES:
        return True
    # gspread stringifies as: APIError: [503]: The service is currently unavailable.
    m = re.search(r"\[(\d{3})\]", str(err))
    return bool(m) and int(m.group(1)) in TRANSIENT_CODES


def retry(fn, attempts: int = 4, base: float = 0.6, sleep=time.sleep):
    """Call fn(), retrying transient Google API errors with exponential backoff.

    `sleep` is injectable so tests do not spend real seconds proving the backoff.
    """
    for n in range(attempts):
        try:
            return fn()
        except Exception as e:
            if not is_transient(e) or n == attempts - 1:
                raise
            sleep(base * (2 ** n))


# ── Rollover ──────────────────────────────────────────────────────────────────
ITEM_TYPE = "item"
CLAIM_TYPE = "rollover"       # bookkeeping row, never displayed


def dedupe_key(person, item):
    return (person, str(item).strip().lower())


def carried_id(source_id, target_week_str: str) -> str:
    """The id a row carried from `source_id` into `target_week_str` will get.

    Deterministic on purpose. Text-only de-duplication cannot survive an edit:
    once someone rewords a carried item, a later rollover no longer recognises
    it, finds no match, and carries the original across a second time. Keying on
    where the row came from is immune to that — the wording can change freely.
    """
    digest = hashlib.sha1(f"{source_id}|{target_week_str}".encode()).hexdigest()
    return "c" + digest[:7]


def _items(df, week_str):
    """Rows of a week that are real items, excluding bookkeeping rows."""
    wk = df[df["week_start"] == week_str]
    if "type" in wk.columns:
        wk = wk[wk["type"].fillna(ITEM_TYPE) == ITEM_TYPE]
    return wk


def rollover_claimed(df_all, week_str: str) -> bool:
    """True if a claim row says the rollover into `week_str` already happened."""
    if df_all is None or df_all.empty or "type" not in df_all.columns:
        return False
    return bool(
        ((df_all["week_start"] == week_str) & (df_all["type"] == CLAIM_TYPE)).any()
    )


def claim_holder(df_all, week_str: str):
    """Of all claims filed for `week_str`, the id that wins. Lowest id takes it.

    Two sessions opening the app seconds apart can both find the week empty and
    both start carrying. Each files a claim and then re-reads; whoever is not the
    holder stands down. Deterministic so both sides reach the same verdict.
    """
    if df_all is None or df_all.empty or "type" not in df_all.columns:
        return None
    claims = df_all[(df_all["week_start"] == week_str) & (df_all["type"] == CLAIM_TYPE)]
    ids = sorted(str(i) for i in claims["id"].tolist())
    return ids[0] if ids else None


def plan_rollover(df_all, last_week_str: str, current_week_str: str):
    """Decide what last week's leftovers should add to this week.

    Returns (to_carry, skipped): rows to append — each already carrying the id it
    should be written with — and how many were already present. Done items never
    carry. A row is considered already present if this week holds either its
    carried id or an item with the same normalised text for that person.
    """
    if df_all is None or df_all.empty:
        return [], 0

    destination = _items(df_all, current_week_str)
    existing_text = {dedupe_key(r["person"], r["item"]) for _, r in destination.iterrows()}
    existing_ids = {str(i) for i in destination["id"].tolist()}

    to_carry, skipped = [], 0
    for _, row in _items(df_all, last_week_str).iterrows():
        if row["status"] == "done":
            continue
        new_id = carried_id(row["id"], current_week_str)
        key = dedupe_key(row["person"], row["item"])
        if new_id in existing_ids or key in existing_text:
            skipped += 1
            continue
        to_carry.append({
            "id": new_id,
            "person": row["person"],
            "item": row["item"],
            "status": row["status"],
        })
        existing_ids.add(new_id)
        existing_text.add(key)
    return to_carry, skipped


def duplicate_ids(df_all, week_str: str):
    """Ids of redundant copies in `week_str`, keeping the first of each group.

    Grouped per person on normalised item text, in sheet order, so the oldest
    copy — the one carrying any edits and status changes — is the survivor.
    """
    if df_all is None or df_all.empty:
        return []
    seen, dupes = set(), []
    for _, row in _items(df_all, week_str).iterrows():
        key = dedupe_key(row["person"], row["item"])
        if key in seen:
            dupes.append(str(row["id"]))
        else:
            seen.add(key)
    return dupes
