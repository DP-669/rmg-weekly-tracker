# rMG Weekly Tracker
Team weekly planner (Monday) and accomplishment tracker (Friday).
Built with Streamlit + Google Sheets.

## Layout
- `core.py` — pure logic (weeks, item text, status, sort, retry, rollover). No
  Streamlit, no network, so it can be tested directly.
- `app.py` — the Streamlit page and the Google Sheets calls.
- `tests/` — pytest over `core.py`.

## Tests
```
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```
They also run on every push and pull request via GitHub Actions.

Each test corresponds to a bug that actually shipped — an unstable sort that
reordered the list on every rerun, a status transition that sent unticked items
to the wrong state, an error classifier that decides what is worth retrying, and
the rollover de-duplication. The comments say which, so a regression fails with
an explanation rather than a bare assertion.

## Setup
1. Add Google Sheets credentials to `.streamlit/secrets.toml`
2. Run: `streamlit run app.py`

## Text size
The app carries its own text-size control — the `A− / A+` pill in the bottom
right. Saved to an iPad Home Screen it runs with no browser chrome, so there is
no Safari text-size control to reach for; this is that control, in the page.

The choice is stored in `localStorage`, so it survives quitting and relaunching
the installed web app. It is per-device, not per-user: it is not written to the
sheet and does not follow you to another iPad or browser.

Item text, names and numbering take the full scale. Control labels ("Done",
"In progress", buttons) scale at half rate — rows are fixed-ratio columns, and
at full scale "In progress" breaks one letter per line.
