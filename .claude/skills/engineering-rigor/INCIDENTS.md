# Incidents

Defects that reached a user. Newest last. Each one is here because it was
shipped, not because it was caught.

Read the **Mechanism** and **Why it escaped** lines — the category is rarely the
useful part. The specific way the verification lied is what generalises.

---

### 2026-08-30 — "fixed" the checkbox colour; it was still visibly wrong
**Context**: Streamlit app, making completed items show a green tick.
**Mechanism**: `accent-color` was set on `input[type=checkbox]`. Streamlit hides
the native input and paints its own `<div>` beside it, so the property had
nothing to colour.
**Why it escaped**: verification read the computed `accent-color` off the input,
saw the right value, and reported success. The rendered tick was still red. A
screenshot taken for an unrelated reason caught it.
**Rule**: verify the artifact, not a proxy. For anything visual, look at the
picture — a computed property is not the rendered result.

---

### 2026-08-30 — three separate stylesheet rules that had never applied
**Context**: same app. Yellow edit buttons, grey delete buttons, an accent bar on
in-progress rows, and green ticks — none rendering, across months of commits.
**Mechanism**: two distinct framework behaviours. (a) `<script>` inside
`st.markdown` is inserted into the DOM but never executed, so a MutationObserver
that was meant to colour ticks had never run — three prior commits had attempted
this fix. (b) `st.markdown('<div class="x">')` renders inside its own container
and does not wrap the widgets that follow, so every descendant selector written
against those wrappers matched nothing.
**Why it escaped**: the CSS and JS were correct as plain web code. Nobody checked
what the framework actually put in the DOM.
**Rule**: for framework-mediated behaviour, write a two-minute probe and inspect
the real DOM before building on assumptions. And when the framework surprises you
once, sweep for other instances — there were three here, not one.

---

### 2026-08-31 — a control placed exactly where the platform puts its own
**Context**: added a floating text-size control, bottom right.
**Mechanism**: Streamlit Cloud pins its "Manage app" toolbar to the bottom right.
On the deployment the two overlapped.
**Why it escaped**: the local test server has none of the hosting platform's
injected UI, so the collision was invisible in every test run.
**Rule**: enumerate what the production environment adds that your sandbox does
not — chrome, toolbars, banners, auth walls — before placing anything fixed to a
viewport corner.

---

### 2026-08-31 — dark mode rendered names black on a black card
**Context**: adding a dark theme to an app that already had a high-contrast mode.
**Mechanism**: the earlier high-contrast rule hardcoded `color: #000` for section
headers. Correct while only a light theme existed; wrong the moment a dark one
did.
**Why it escaped**: caught by a screenshot, not by reasoning. Nothing had swept
the stylesheet for literals that assumed a light background.
**Rule**: when adding a second mode/theme/state, grep for literals that encode an
assumption about the first. Tokens exist so a second mode is one override block;
a literal is a landmine waiting for that second mode.

---

### 2026-08-31 — a state-specific rule repainted every state
**Context**: same dark theme. Unchecked checkboxes were invisible on dark cards.
**Mechanism**: the fix styled `label > span + div` without scoping to unchecked,
so it also repainted *checked* boxes, wiping out the green tick and the
in-progress colour that had just been fixed.
**Why it escaped**: the rule was written for the case being fixed, without asking
what else it selected.
**Rule**: state-dependent styling must be scoped to the state. After writing a
selector, ask what else it matches.

---

### 2026-09-08 — outage: ImportError on a deployed app
**Context**: shipped a change that added four names to a helper module and
imported them in the same commit.
**Mechanism**: the framework re-runs the main script on every interaction but
keeps imported local modules cached in `sys.modules`. The running process held
the previous version of the module, so the new main script asked it for names it
did not have. Every rerun failed until a manual reboot.
**Why it escaped**: correct on a fresh checkout, and CI passed. The local test
harness restarts the server on every run, so it could not reproduce a
long-running process. Nobody asked how the code reaches the running system.
**Rule**: know the deploy and reload model of the target runtime. A change that
is correct in the repo can still break the running system, and "tests pass" says
nothing about that path.

---

### 2026-09-08 — declared duplicates fixed while two causes remained
**Context**: duplicate rows appearing in a shared spreadsheet-backed app.
**Mechanism**: three independent causes. (1) De-duplication matched on item
*text*, so editing a row made a later pass fail to recognise it and re-copy the
original. (2) The "run only once" guard lived in per-session state, so every
browser and device could run it, and the one shared check was false during the
seconds the first writer was still writing. (3) Rows whose `type` cell was blank
— hand-added rows, and rows from before that column was always populated — were
excluded by a `type == "item"` filter, so they were invisible both to
de-duplication and to the carry-over logic.
**Why it escaped**: causes 1 and 2 were found and fixed, and the work was
reported as done. Cause 3 was still live, so the user saw duplicates again after
being told they were fixed. No fixture contained a blank cell.
**Rule**: two rules. Prefer stable identity over mutable content when matching
records. And when you find one cause of a symptom, keep looking — report "fixed
these two causes" rather than "fixed", until the symptom is actually gone.

---

### 2026-09-08 — a passing-looking test asserted the wrong thing
**Context**: testing that typed HTML in user content renders inert.
**Mechanism**: the assertion was `"<a href=" not in output`, which fails on
correct behaviour — a URL inside the hostile text legitimately auto-links. A
second attempt asserted `"onclick=" not in output`, which fails on the escaped
text that *displays* the word.
**Why it escaped**: the failure was read as a code bug rather than a test bug,
twice.
**Rule**: when a test fails, read the actual output before changing the code. Then
make the assertion say precisely what is meant — `'onclick="' not in out`
distinguishes a live attribute from displayed text; `"onclick"` does not.

---

### 2026-09-08 — every mistake above reached production immediately
**Context**: eight changes over one session, each merged straight to the branch
that auto-deploys, without being asked to.
**Mechanism**: no gate between "I believe this works" and "the user's live app is
running it". The user became the test environment and found the defects.
**Why it escaped**: not a technical failure. A default of shipping on my own
authority.
**Rule**: do not merge to a deploying branch without the owner's go-ahead. Push
the branch, state what was verified and what was not, let them decide. Permission
to ship one change is not permission for the next.


### 2026-09-08 — dark mode shipped with text at 1.68:1, and duplicates still recurring
**Context**: same tracker. Two reports in one message: names in the top bar
almost invisible on the dark theme, and duplicate rows that the user does not
want to manage at all.
**Mechanism**: (a) theme colours were applied by enumerating selectors. Anything
nobody thought to name kept Streamlit's default `rgb(49,51,63)` — fine on white,
1.68:1 on black. Four elements: three radio labels and the week date. (b) Every
write path minted a random id, so nothing at the data layer made a repeated
write resolve to the same row; de-duplication was a banner the user had to
notice, scroll to, and act on.
**Why it escaped**: (a) the earlier contrast work measured the elements that had
been *noticed* and reported "everything clears AA" — a claim about a sample,
stated as a claim about the page. Two rounds of visual fixes had already been
shipped and neither swept the whole DOM. (b) removing the duplicates was treated
as the goal; not creating them was left to logic that could still be raced.
**Rule**: two, and both are sharpenings of rules already here.
*Reinforces "fix the class, not the instance"* — when the class is "text that
kept a default colour", the only honest check enumerates the rendered DOM, not
the selectors you wrote. Contrast is now audited by
`tools/audit_contrast.py`, which walks every text node in all four theme
combinations; it found the four failures immediately, and caught a regression
the same fix introduced.
*New*: when a user says they do not want to manage a recurring problem, the
deliverable is that the problem cannot occur, not a better way to clean it up.
Prefer a structural guarantee — here, ids derived from row content, so a repeated
write is the same row — with automatic self-healing as the backstop. A control
that asks the user to act is a last resort, not a solution.

---

### 2026-09-08 — a fix sat unmerged because the message buried it
**Context**: a verified fix left in a PR behind a review gate.
**Mechanism**: the reply opened with "not merged — say the word", then three
sections describing the fix in detail. The user reasonably read it as shipped,
rebooted the app, and saw the same broken screen.
**Why it escaped**: the status was accurate and present. It was buried under
length, so it was never read. Long replies are not thorough, they are unread —
and the user then acts on a wrong picture.
**Rule**: state blocked-or-not-live in the first line, alone. And by default keep
replies short: result, problems, what is needed. Detail on request only. Length
spent explaining reasoning is length the reader spends finding the one fact that
changes what they do.

---

### 2026-09-08 — add-item box broke: "'str' object is not callable"
**Context**: adding `item_id()` to make writes idempotent.
**Mechanism**: two faults stacked. The edit that was supposed to add `item_id`
to app.py's import list used a plain `str.replace` whose pattern did not match
the file's actual indentation, so it silently changed nothing. The name then
resolved to a loop-local `item_id = row["id"]` — a string — and calling it
raised. In the other call site, outside that loop, it was simply undefined.
**Why it escaped**: unit tests import `core`, never the Streamlit script, so
nothing exercised app.py at all. The browser checks that were run drove display
and de-duplication but never typed into the add box — the one path the change
was actually for. `pyflakes app.py` reports it in under a second.
**Rule**: three. An edit that must match existing text needs an assertion that it
matched; a silent no-op edit is worse than a crash. Exercise the path the change
is *for*, not the paths that are easy to drive. And a linter that sees the file
your tests never import is cheap coverage for exactly the gap between them —
pyflakes now runs in CI over app.py.
