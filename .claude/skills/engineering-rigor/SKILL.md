---
name: engineering-rigor
description: Hard-won rules for not shipping broken work, derived from real defects that reached real users. Use this whenever fixing a bug, changing code that is already deployed or in use, styling or theming a UI, working against a live datastore (spreadsheet, database, API), or preparing to merge, deploy, or tell someone a change is done. Also use before claiming any fix works, before saying a task is complete, and when a user reports that a previous fix did not hold. Consult it even for changes that look small or obvious — the defects catalogued here all came from changes that looked small.
---

# Engineering rigor

Every rule here exists because the failure it describes actually happened, was
shipped, and cost a real person real time. `INCIDENTS.md` holds the record.

The point is not ceremony. The point is that a specific, recurring set of
mistakes is what turns "I fixed it" into three more rounds of the user finding
your errors for you. Those rounds destroy trust far faster than the original bug.

## The habit underneath all of it

Almost every defect below came from acting on the first framing of the problem.
The symptom is in front of you, a plausible cause suggests itself, you fix that,
and you ship — never asking what *else* is true.

Before acting, spend a moment on three questions. They are cheap and they are
where the leverage is:

1. **What class of problem is this?** Not "this checkbox is the wrong colour" but
   "styling I wrote is not reaching the element I think it is". Then: *where else
   does that class apply?* Sweep for the whole class before shipping. Fixing one
   instance of a three-instance bug and announcing victory is worse than not
   fixing it, because now everyone believes it is handled.

2. **What am I assuming?** About how the framework behaves, about the shape of
   the data, about the environment the code will run in. Each assumption is a
   place the fix can be silently wrong. Name them, then check the ones that would
   invalidate the whole change.

3. **How could my verification be lying to me?** A green check that measures the
   wrong thing is more dangerous than no check, because it converts a doubt into
   a false certainty you then pass to the user.

## Verify the artifact, not a proxy

The most expensive single mistake in the record: reading a computed CSS property,
seeing the correct value, and reporting the fix as working — while the rendered
element was still visibly wrong, because the framework painted its own element
over the one being measured. A screenshot caught it. The property check did not.

Verification has a ladder. Climb as high as the change warrants:

| Level | What it proves | When it is enough |
|---|---|---|
| It parses / imports | Syntax | Never, on its own |
| Unit tests on pure logic | The logic is right | Pure functions with no environment |
| Integration against a fake | The wiring is right | Logic + I/O, when the fake is faithful |
| Drive the real interface | The user-visible behaviour is right | Anything with a UI |
| Look at the output | What the user actually sees | Anything visual — always |

For visual work, **look at the picture**. Take the screenshot and read it. Do not
substitute a numeric check for looking, and do not skip looking because the
numeric check passed. In the record there are two separate cases where the
numbers were right and the picture was wrong.

## Assume the framework is not doing what you think

Anything mediated by a framework — CSS through a component library, imports in a
long-running server, caching decorators, template rendering — behaves in ways
that are not inferable from the language or from HTML semantics. The record has
five separate defects of exactly this kind, all shipped by reasoning about how it
*ought* to work.

The fix is cheap and takes two minutes: **write a throwaway probe.** Render one
element, inspect what actually reached the DOM or the module table, then build on
what you observed. That probe is worth more than an hour of reading source.

When you find that the framework surprised you once, assume it surprised you
elsewhere too and go looking. See `references/framework-traps.md` for the
specific traps already found.

## Assume the data is messy

Code that reads a live store — a spreadsheet, a database someone edits by hand, an
API with years of history — meets rows that predate the current schema, cells
that are empty strings rather than nulls, text with stray whitespace and
inconsistent case, and records people edited manually.

Two shipped defects came from clean-data assumptions: matching rows by exact text
(which breaks the moment anyone edits the text), and requiring a field to equal a
specific value (which silently skipped every row where that cell was blank).

So: prefer stable identity over mutable content when matching records. Treat
unrecognised values as data rather than filtering them out — exclude what you
know is special, keep everything else. And build at least one test fixture that
is deliberately messy: blank fields, mixed case, padding, legacy shapes.

## Know how your change reaches production

A change that is correct in the repository can still break the running system.
The record contains an outage caused by adding names to a module and importing
them in the same commit — correct on a fresh checkout, fatal against a
long-running process that had the old module cached.

Before shipping, answer: how does this code get from the repo into the running
system? Does that process restart cleanly, or does state survive? Is there an
ordering where half the change is live? If you cannot answer, that is the risk,
and it belongs in what you tell the user.

## Your test environment is not their environment

Enumerate the differences and say which of your claims they could invalidate.
Real examples from the record: a local server restarts fresh every run, so it
could never reproduce a stale-module bug; a local page has none of the hosting
platform's own injected UI, so a control was placed exactly where the platform
puts its toolbar; the test browser was not the user's browser.

You do not have to eliminate these gaps. You do have to know them and disclose
them, so the user's confidence matches the evidence.

## Do not ship to production on your own authority

Merging to the branch that auto-deploys puts every mistake in front of the user
immediately, and turns them into your test environment. That is what makes a
sequence of ordinary bugs feel like incompetence.

Push the branch, open the change, say what you verified and what you did not, and
let the owner decide. The exception is when they have said to ship — and that
permission covers this change, not every future one.

## Scope your claims to what you checked

"Fixed" means the specific thing you verified, by the means you verified it. If
you fixed one of three causes, say one of three. If your test was a fake, say it
was a fake. If you could not test on their platform, say so.

Overclaiming is the mechanism by which one bug becomes a credibility problem: the
user believes the matter is closed, builds on it, and discovers otherwise.

## When a test fails, suspect the test

Twice in the record a failing assertion was the assertion being wrong, not the
code. Before changing the code to satisfy a test, read the actual output and ask
what the correct behaviour is. Then make the assertion say that precisely —
`'onclick="' not in out` is a real claim; `"onclick" not in out` fails on text
that merely displays the word.

## Before you say it is done

- The change is verified at the highest rung of the ladder the change warrants.
- You swept for other instances of the same class of bug.
- Assumptions about framework, data and environment were checked or disclosed.
- What you tell the user distinguishes verified from assumed.
- Nothing reached production without the owner's go-ahead.

## Keeping this skill alive

This file is only worth what the last incident taught it. **Whenever a defect of
yours reaches the user — they report a bug in your work, a fix does not hold, or
you shipped something broken — append an entry to `INCIDENTS.md` before moving
on.** Do it while the cause is fresh; the value is in the specific mechanism, not
the category.

Entry format:

```markdown
### YYYY-MM-DD — one-line symptom
**Context**: what was being built, in what stack
**Mechanism**: the actual cause, precisely
**Why it escaped**: what verification was done, and what it failed to catch
**Rule**: the generalisation — or "reinforces: <existing rule>"
```

Then look at the entry with fresh eyes. If it is a new class, add a section
above. If it reinforces an existing rule, note that instead — a rule that keeps
recurring needs sharpening or a check that makes it automatic, not a duplicate.
Prune rules that stop earning their place; a long list nobody reads protects
nobody.

## References

- `INCIDENTS.md` — the record. Read it when starting work in a stack that appears
  there, and when a fix of yours does not hold.
- `references/framework-traps.md` — specific traps found in specific frameworks,
  and the probes that reveal them. Read before styling or debugging in a stack
  listed there.
