# rMG Weekly Tracker
Team weekly planner (Monday) and accomplishment tracker (Friday).
Built with Streamlit + Google Sheets.

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
