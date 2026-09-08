# Framework traps

Behaviours that are not inferable from the language or from ordinary web
semantics, found the hard way. Each entry has a probe: a small thing to run that
shows you the truth in a couple of minutes, so you build on an observation
instead of an assumption.

The general lesson matters more than the list. Any framework that renders your
markup, caches your modules, or wraps your widgets has behaviours like these. The
list is short because it only contains what has actually bitten; treat it as
evidence that probing is worth it, not as a complete catalogue.

## Contents

- [Probing technique](#probing-technique)
- [Streamlit](#streamlit)
- [CSS through any component library](#css-through-any-component-library)
- [Spreadsheets used as a database](#spreadsheets-used-as-a-database)

---

## Probing technique

Before writing code that depends on how a framework renders or loads something,
build the smallest possible instance of it and inspect reality.

For anything that renders to a browser, a headless browser is the tool: render
one widget, then ask the page what actually exists — which element carries the
class, what the computed style is, which element is the parent, whether the
script ran. Ten lines, two minutes, and it replaces a whole class of guesswork.

Two rules make probes worth the time:

- **Probe the thing you will build on**, not a simplified version of it. A probe
  of a bare `<div>` tells you nothing about how the framework wraps its widgets.
- **Then look at the rendered result too.** A probe reads properties; properties
  can be right while the picture is wrong. Both, not either.

---

## Streamlit

**`<script>` inside `st.markdown` never executes.** The tag is inserted into the
DOM, so it looks like it worked, but scripts injected via innerHTML do not run.
Anything needing real JavaScript belongs in `st.components.v1.html`, which runs in
a same-origin iframe and can reach `window.parent.document` and
`window.parent.localStorage`. Elements appended to `parent.document.body` survive
reruns, because they sit outside the framework's React root.

**`<style>` inside `st.markdown` does work.** Style elements apply when inserted
via innerHTML; scripts do not. So CSS-only solutions are the reliable path.

**An unclosed `<div>` from `st.markdown` does not wrap what follows.** Each
`st.markdown` call renders into its own container and the browser closes the tag
there. `st.markdown('<div class="x">')` … widget … `st.markdown('</div>')`
produces an empty `.x` div and an unwrapped widget, so every descendant selector
written against it silently matches nothing.

**Target widgets by key instead.** Widgets given a `key` get a `st-key-<key>`
class on their container element, which is a stable hook:
`[class*="st-key-myprefix_"] button { … }`. This is the reliable replacement for
wrapper divs. Available from Streamlit 1.39.

**Streamlit sets `font-family` on its own markdown containers.** That beats
anything inherited from `body`, so an app-wide font set on `body` never reaches
rendered content. Target `[data-testid="stMarkdownContainer"]` and descendants —
and exclude ligature icon elements (`[data-testid="stIconMaterial"]`), or the
icons render as their literal ligature names.

**The visible border and fill of a text input belong to a wrapper div**, not the
`<input>`. Theming the input alone leaves a bright box. `div:has(> input)` matches
it robustly across versions, where generated class names do not.

**Widget state ignores `value=` once the key exists.** `st.checkbox(value=x,
key=k)` uses `x` only on first render; afterwards `session_state[k]` wins. If the
underlying data changed, the widget keeps showing the old state. Including the
relevant state in the key makes the widget re-read when that state changes.

**`@st.cache_data` ignores arguments whose names start with an underscore.** A
parameter named `_cache_key` does not vary the cache entry — every call shares
one. Errors returned (rather than raised) from a cached function get cached too;
`@st.cache_resource` has no TTL, so a cached failure persists for the life of the
process.

**Imported local modules stay in `sys.modules` across reruns.** The main script
re-runs; your helper module does not reload. A deploy that adds names to a helper
and imports them in the same commit can fail against the still-running process
until it is rebooted. `importlib.reload(module)` before importing from it removes
the failure mode.

**Streamlit Cloud pins its own toolbar to the bottom right.** Fixed-position UI
belongs somewhere else.

---

## CSS through any component library

The recurring shape: the element you can select is not the element that renders.
Libraries hide native inputs and paint substitutes, wrap fields in styled
containers, and set properties directly on their own nodes.

- Before styling a control, inspect its actual DOM: which node has the
  background, which is the accessible input, which carries state.
- Style state with a state-aware selector (`label:has(input:checked)`), and check
  what else your selector matches — an unscoped rule will hit every state.
- `:has()` is widely supported now (Safari 15.4+) and is usually the honest way
  to express "the wrapper of a checked input".
- Prefer semantic or framework-stable hooks (`data-testid`, key-derived classes)
  over generated class names, which change between releases.

---

## Spreadsheets used as a database

- **Empty cells read as `""`, not null.** Filters like `type == "item"` silently
  drop every row where a human left the cell blank, or that predates the column.
  Prefer excluding what you know is special and keeping everything else.
- **Values are user-editable at any moment.** Matching records by their text
  breaks as soon as someone edits the text. Match on a stable id; derive one
  deterministically if the store has no spare column.
- **There is no transaction and no lock.** Two clients can read the same state and
  both write. If an operation must happen once, record that decision in the store
  itself and re-read to confirm you hold the claim; per-session flags cannot
  coordinate across devices.
- **Values get coerced.** Numeric-looking ids may come back as numbers, so a
  lookup by string can miss.
- **Row indices shift on delete.** Delete bottom-up, or re-resolve each row.
- **Quotas are real.** Deleting fifty rows one call at a time can trip rate
  limits; read once, then act.
