# CLAUDE.md

Guidance for Claude Code and other AI assistants working in this repository.

## What this is

**rMG Weekly Tracker** — a small internal Streamlit app for a three-person team
(Vesna, Craig, Damir) to track weekly plans and accomplishments. Google Sheets is
the only database. Deployed on Streamlit Community Cloud.

The entire application is **one file: `app.py` (~660 lines)**. There is no package
structure, no test suite, no linter config, and no CI. Treat `app.py` as the whole
codebase.

```
app.py            # everything: CSS, constants, data layer, handlers, UI
requirements.txt  # streamlit, gspread, google-auth, pandas (floors only, unpinned)
README.md         # two-line setup note
.gitignore        # notably: .streamlit/secrets.toml
```

## Running locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Requires `.streamlit/secrets.toml` (gitignored, never commit it):

```toml
CHAT_ADD_TOKEN = "some-shared-secret"   # optional, enables the URL add endpoint

[GOOGLE]                                 # service-account JSON, key-for-key
type = "service_account"
project_id = "..."
private_key = "..."
client_email = "...@....iam.gserviceaccount.com"
# ...remaining service-account fields
```

The service account's `client_email` must be granted edit access to the Google
Sheet named **`rMG Weekly Tracker`** (constant `SHEET_NAME`); the app uses
`sheet1`. Without `[GOOGLE]` the app renders a "not configured" warning and calls
`st.stop()`.

There is no way to run this offline — every code path that touches data hits the
live Sheets API. Verify changes by reading the code and by running the app against
a scratch sheet; do not assume a change works because it imports cleanly.

## Architecture

`app.py` reads top-to-bottom in this order, and Streamlit re-executes the whole
file on every interaction:

1. `linkify()` — turns markdown links and bare URLs into `<a>` tags.
2. `st.set_page_config` + one large `st.markdown` block of CSS and a `<script>`.
3. Constants: `TEAM`, `RMG_PERSON`, `SHEET_NAME`, `COLS`.
4. Sheets layer: `_get_worksheet` / `get_sheet` / `load_data` / `invalidate_cache`
   / `append_row` / `update_row` / `delete_row`.
5. Session-state initialization.
6. Pre-render handlers: `_handle_chat_add()`, `_auto_rollover_if_needed()`.
7. Top bar (user radio, week nav, rollover button), then the data load.
8. `render_items()` — the single renderer for every list.
9. One `st.expander` per person in `TEAM`, then the shared `rMG` expander.

Because the script is re-run on every widget change, all mutations follow the same
pattern: **write to the sheet → `invalidate_cache()` → `st.rerun()`.**

## Data model

One flat sheet. Column order is defined by `COLS` and is **load-bearing**:

| column       | notes                                                    |
|--------------|----------------------------------------------------------|
| `id`         | first 8 chars of a `uuid4`. **Must stay column 1.**       |
| `person`     | one of `TEAM` or `"rMG"`                                  |
| `week_start` | ISO date of that week's Monday (`get_monday`)             |
| `type`       | always `"item"` (vestigial; kept for schema stability)    |
| `item`       | free text; may contain markdown links or bare URLs        |
| `status`     | `"pending"` \| `"in_progress"` \| `"done"`                |
| `created_at` | ISO date                                                  |
| `updated_at` | ISO date, refreshed by `update_row`                       |

Why the order matters:

- `update_row` and `delete_row` locate rows with `ws.find(str(row_id), in_column=1)`,
  so `id` must be the first column.
- `update_row` computes the target cell as `COLS.index(field) + 1`, so `COLS` must
  match the physical sheet header exactly.

**If you add a column, append it to the end of `COLS`** and repair the live sheet's
header row by hand. Note that `_get_worksheet` only *inserts* a header when
`ws.row_values(1) != COLS` — it never replaces one. A stale header therefore gets
pushed down and survives as a junk data row.

## Conventions and non-obvious behavior

Most of these are fixes for specific bugs; changing them tends to reintroduce the
bug. Check `git log` before "simplifying" any of them.

**Caching.** `_get_worksheet` is `@st.cache_resource` so exactly one authorized
`gspread` client exists per session — this was added to stop Sheets API 429s. Never
build a client inline; always go through `get_sheet()`, which returns a
`(worksheet, error)` tuple that callers must unpack and check.

**`load_data`'s cache key does nothing.** It is `@st.cache_data(ttl=60)` taking
`_cache_key`, and Streamlit excludes underscore-prefixed parameters from its hash.
Every caller — `"rollover"`, `"auto_check"`, `current_week_str` — therefore shares a
single cache entry holding the *whole* sheet. That is fine because the app filters
by week in memory, but it means the string you pass is documentation, not
invalidation. Only `invalidate_cache()` (i.e. `load_data.clear()`) actually busts it.

**Widget keys.** In `render_items`, keys are built as
`rk = f"{add_key}_{i}_{item_id}"` — section name plus 1-based position. Rollover can
legitimately produce two rows sharing an `id`, so `item_id` alone is not unique and
a key collision crashes the render. Keep the section+index prefix.

**`add_key` is overloaded.** It is simultaneously the widget-key namespace and the
value written to the `person` column (`person_label = add_key`). Only pass a real
person name.

**Clearing text inputs.** Streamlit forbids assigning to a widget's `session_state`
value after instantiation, so the add-item box is cleared by *cycling its key*:
`st.session_state[f"input_n_{add_key}"] += 1` creates a fresh widget. Do not try to
blank the value directly.

**Green "Done" checkboxes.** Streamlit's generated DOM makes `nth-child` CSS
fragile, so an inline `<script>` with a `MutationObserver` walks
`[data-testid="stCheckbox"]` and sets `accentColor` on any checkbox labelled
`Done`. It re-runs on every DOM mutation because Streamlit rebuilds nodes freely.

**`linkify` double-conversion.** It converts `[label](url)` first, then splits the
string around existing `<a>…</a>` tags with a capturing regex and only linkifies the
even-indexed (plain-text) segments. Without the split, URLs inside freshly created
anchors get wrapped a second time. Keep the split if you touch this function.

**HTML is not escaped.** Item text goes through `linkify` into
`unsafe_allow_html=True`. Anyone who can add an item can inject HTML. This is
accepted for a private three-person tool — but do not extend the app to untrusted
input without adding escaping first.

## Permissions

Honor-system only; there is no authentication.

- "You are:" is a radio button, freely switchable.
- A person's own section is editable when `is_me and is_current_week`.
- The shared `rMG` section is editable by anyone during the current week.
- Any non-current week is fully read-only (`is_current_week` gates checkboxes and
  the add-item input).

## Rollover

`_do_rollover(current_week, current_week_str, force=False)` copies every item from
the previous Monday's week that is **not** `done` into the current week as new rows
with new ids, preserving `status`.

It is idempotent: the dedupe key is `(person, item.strip().lower())` against rows
already in the destination week. `force=True` (the "Weekly Rollover" button) surfaces
a carried/skipped summary; `force=False` stays silent.

`_auto_rollover_if_needed` runs once per week per session, guarded by the
`_auto_ro_{week_start}` session-state flag. It fires only when viewing the real
current week, the current week has zero rows, and the previous week has some. It
swallows exceptions deliberately — a failed auto-rollover must not break page load.

## Chat-add URL endpoint

`_handle_chat_add()` runs before render and reads
`?add_to=<person>&item=<text>&token=<secret>`.

- The token must match `st.secrets["CHAT_ADD_TOKEN"]`; a missing or empty secret
  disables the endpoint entirely.
- `add_to` must be in `TEAM + [RMG_PERSON]`.
- Adds to the *real* current week regardless of which week is being viewed.
- Deduped case-insensitively against that week.
- `st.query_params.clear()` is called on **every** exit path so a refresh cannot
  replay the write. Preserve that.

## Working in this repo

- History on `main` is linear and unsquashed — small, single-purpose commits, no
  merge commits and no PR history to date. Automated/assistant changes should still
  go to a feature branch and be pushed with `git push -u origin <branch>`.
- Commit messages follow the existing loose style — `fix:` / `feat:` / `style:`
  prefixes appear on some commits, plain imperative sentences on others. Match the
  neighbors rather than imposing a new convention.
- Keep everything in `app.py` unless the change genuinely warrants a module; the
  single-file layout is intentional for a tool this size.
- CSS lives in the one `st.markdown` block near the top. The palette is
  Apple-system-like: `#007AFF` blue (accent/self), `#34C759` green (done),
  `#FF9500` orange (in progress), `#FF3B30` red (delete hover), `#8E8E93` grey
  (muted), `#F2F2F7` page background, `#E5E5EA` borders. Font is DM Sans.
- Every Sheets write costs API quota and each status toggle triggers a rerun
  (`update_row` alone writes two cells). Be deliberate about adding write paths.
- There are no tests. If you change data-layer logic, say plainly that it is
  unverified rather than implying it was tested.
