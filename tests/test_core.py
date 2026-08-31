"""Tests for core.py.

Each block here corresponds to a bug that actually shipped. The comments say
which one, so a future change that reintroduces it fails with an explanation
rather than a bare assertion.
"""

import re
from datetime import date

import pandas as pd
import pytest

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


def rows(*specs):
    """Build a frame from (id, person, week, item, status) tuples."""
    return pd.DataFrame(
        [
            {"id": i, "person": p, "week_start": w, "type": "item",
             "item": it, "status": s, "created_at": w, "updated_at": w}
            for i, p, w, it, s in specs
        ],
        columns=COLS,
    )


# ── Weeks ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("day", range(7))
def test_get_monday_lands_on_monday_all_week(day):
    d = date(2026, 8, 24)  # a Monday
    assert get_monday(date.fromordinal(d.toordinal() + day)) == d


def test_format_week_spans_monday_to_sunday():
    assert format_week(date(2026, 8, 24)) == "Aug 24 – Aug 30, 2026"


# ── sort_items ────────────────────────────────────────────────────────────────
def test_sort_groups_in_progress_then_pending_then_done():
    df = rows(("1", "D", "w", "a", "done"),
              ("2", "D", "w", "b", "pending"),
              ("3", "D", "w", "c", "in_progress"))
    assert list(sort_items(df)["id"]) == ["3", "2", "1"]


def test_sort_is_stable_within_a_status():
    """The shipped bug: default quicksort re-permuted equal-status items, so the
    list reordered itself on every rerun and position-keyed widgets followed."""
    df = rows(*[(str(n), "D", "w", f"item {n}",
                 ["pending", "done", "in_progress"][n % 3]) for n in range(30)])
    first = list(sort_items(df)["id"])
    for _ in range(5):
        assert list(sort_items(df)["id"]) == first
    # and equal-status items stay in sheet order
    pend = [r.id for _, r in df.iterrows() if r.status == "pending"]
    assert [i for i in first if i in set(pend)] == pend


def test_sort_treats_unknown_status_as_pending():
    df = rows(("1", "D", "w", "a", "done"), ("2", "D", "w", "b", "whatever"))
    assert list(sort_items(df)["id"]) == ["2", "1"]


def test_sort_of_empty_frame_is_empty():
    assert sort_items(rows()).empty


def test_sort_does_not_mutate_its_input():
    df = rows(("1", "D", "w", "a", "done"), ("2", "D", "w", "b", "pending"))
    before = df.copy()
    sort_items(df)
    pd.testing.assert_frame_equal(df, before)


# ── next_status ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status,done,prog,want", [
    ("pending",     True,  False, "done"),
    ("pending",     False, True,  "in_progress"),
    ("in_progress", True,  True,  "done"),         # tick Done while In progress is on
    ("in_progress", False, False, "pending"),
    ("done",        True,  True,  "in_progress"),  # tick In progress on a done item
    ("done",        False, False, "pending"),
    ("pending",     False, False, "pending"),      # no-op rerun
    ("done",        True,  False, "done"),         # no-op rerun
    ("in_progress", False, True,  "in_progress"),  # no-op rerun
])
def test_next_status(status, done, prog, want):
    assert next_status(status, done, prog) == want


def test_unticking_done_goes_to_pending_not_in_progress():
    """The shipped bug: reading both boxes at once meant a stale In-progress
    value caught the fall-through, so unticking Done reopened the item as
    in-progress instead of pending."""
    assert next_status("done", False, True) == "pending"


# ── linkify ───────────────────────────────────────────────────────────────────
def test_linkify_escapes_markup():
    out = linkify("<img src=x onerror=alert(1)>")
    assert "<img" not in out
    assert "&lt;img" in out


def test_linkify_escapes_quotes_and_ampersands():
    out = linkify('a & b "c"')
    assert "&amp;" in out and "&quot;" in out


def test_linkify_converts_a_bare_url():
    out = linkify("see https://example.com/x")
    assert '<a href="https://example.com/x" target="_blank">' in out


def test_linkify_converts_a_markdown_link():
    assert '<a href="https://example.com" target="_blank">report</a>' in \
        linkify("[report](https://example.com)")


def test_linkify_does_not_double_convert():
    """A markdown link's URL must not be linkified again inside its own anchor."""
    out = linkify("[report](https://example.com)")
    assert out.count("<a ") == 1


def test_linkify_leaves_plain_text_alone():
    assert linkify("just a task") == "just a task"


def test_linkify_accepts_non_strings():
    assert linkify(42) == "42"


def test_linkify_neutralises_a_typed_anchor_tag():
    """A raw <a> typed into an item must render as inert text.

    The URL inside it still auto-links — that is the same thing that happens if
    the URL is typed on its own, and the attacker controls no markup either way.
    What must not survive is their tag: no attribute of theirs reaches the DOM.
    """
    out = linkify('<a href="https://evil.example" onclick="steal()">x</a>')
    assert "&lt;a href=" in out            # their tag is text
    # their handler survives only as escaped text (&quot;), never as a real
    # attribute — a real one would carry a raw quote
    assert 'onclick="' not in out
    # every real anchor points at the bare URL and nothing else
    hrefs = re.findall(r'<a href="([^"]*)"', out)
    assert hrefs == ["https://evil.example"]


def test_linkify_refuses_non_http_schemes():
    """javascript: and data: must never become links."""
    for hostile in ("javascript:alert(1)", "data:text/html,<script>x</script>"):
        out = linkify(hostile)
        assert "<a " not in out


# ── is_transient ──────────────────────────────────────────────────────────────
class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class ErrWithResponse(Exception):
    def __init__(self, status_code):
        super().__init__("boom")
        self.response = FakeResponse(status_code)


THE_REPORTED_ERROR = "APIError: [503]: The service is currently unavailable."


def test_the_error_from_the_bug_report_is_transient():
    assert is_transient(THE_REPORTED_ERROR)
    assert is_transient(Exception(THE_REPORTED_ERROR))


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_codes(code):
    assert is_transient(Exception(f"APIError: [{code}]: busy"))
    assert is_transient(ErrWithResponse(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_real_errors_are_not_transient(code):
    """A permission or bad-request failure must surface at once, not stall
    behind four seconds of pointless retries."""
    assert not is_transient(Exception(f"APIError: [{code}]: nope"))
    assert not is_transient(ErrWithResponse(code))


def test_non_api_errors_are_not_transient():
    assert not is_transient(ValueError("nope"))
    assert not is_transient("setup")          # the not-configured sentinel
    assert not is_transient("")


# ── retry ─────────────────────────────────────────────────────────────────────
def test_retry_returns_immediately_on_success():
    calls = []
    assert retry(lambda: calls.append(1) or "ok", sleep=lambda _: None) == "ok"
    assert len(calls) == 1


def test_retry_recovers_from_transient_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception(THE_REPORTED_ERROR)
        return "rows"

    assert retry(flaky, sleep=lambda _: None) == "rows"
    assert calls["n"] == 3


def test_retry_gives_up_after_the_attempt_budget():
    calls = {"n": 0}

    def always():
        calls["n"] += 1
        raise Exception(THE_REPORTED_ERROR)

    with pytest.raises(Exception, match=r"\[503\]"):
        retry(always, attempts=4, sleep=lambda _: None)
    assert calls["n"] == 4


def test_retry_does_not_retry_a_real_error():
    calls = {"n": 0}

    def forbidden():
        calls["n"] += 1
        raise Exception("APIError: [403]: forbidden")

    with pytest.raises(Exception, match=r"\[403\]"):
        retry(forbidden, sleep=lambda _: None)
    assert calls["n"] == 1


def test_retry_backs_off_exponentially():
    waits = []

    def always():
        raise Exception(THE_REPORTED_ERROR)

    with pytest.raises(Exception):
        retry(always, attempts=4, base=0.6, sleep=waits.append)
    assert waits == [0.6, 1.2, 2.4]


# ── plan_rollover ─────────────────────────────────────────────────────────────
LAST, THIS = "2026-08-17", "2026-08-24"


def test_rollover_carries_unfinished_work_and_leaves_done_behind():
    df = rows(("1", "Damir", LAST, "chase BMG", "pending"),
              ("2", "Damir", LAST, "file statements", "done"),
              ("3", "Vesna", LAST, "draft deck", "in_progress"))
    carry, skipped = plan_rollover(df, LAST, THIS)
    assert [(c["person"], c["item"]) for c in carry] == \
        [("Damir", "chase BMG"), ("Vesna", "draft deck")]
    assert skipped == 0


def test_rollover_preserves_in_progress_status():
    df = rows(("1", "Damir", LAST, "chase BMG", "in_progress"))
    carry, _ = plan_rollover(df, LAST, THIS)
    assert carry[0]["status"] == "in_progress"


def test_rollover_is_idempotent():
    """Running it twice must not duplicate — this is the whole point."""
    df = rows(("1", "Damir", LAST, "chase BMG", "pending"),
              ("2", "Damir", THIS, "chase BMG", "pending"))
    carry, skipped = plan_rollover(df, LAST, THIS)
    assert carry == [] and skipped == 1


def test_rollover_dedupe_ignores_case_and_padding():
    df = rows(("1", "Damir", LAST, "  Chase BMG  ", "pending"),
              ("2", "Damir", THIS, "chase bmg", "pending"))
    carry, skipped = plan_rollover(df, LAST, THIS)
    assert carry == [] and skipped == 1


def test_rollover_dedupe_is_per_person():
    """Same wording for two people is two real tasks."""
    df = rows(("1", "Damir", LAST, "chase BMG", "pending"),
              ("2", "Vesna", THIS, "chase BMG", "pending"))
    carry, skipped = plan_rollover(df, LAST, THIS)
    assert len(carry) == 1 and carry[0]["person"] == "Damir" and skipped == 0


def test_rollover_collapses_duplicates_within_the_source_week():
    df = rows(("1", "Damir", LAST, "chase BMG", "pending"),
              ("2", "Damir", LAST, "chase BMG", "pending"))
    carry, skipped = plan_rollover(df, LAST, THIS)
    assert len(carry) == 1 and skipped == 1


def test_rollover_ignores_other_weeks():
    df = rows(("1", "Damir", "2026-08-10", "ancient task", "pending"))
    assert plan_rollover(df, LAST, THIS) == ([], 0)


def test_rollover_of_empty_history_is_a_no_op():
    assert plan_rollover(rows(), LAST, THIS) == ([], 0)
    assert plan_rollover(None, LAST, THIS) == ([], 0)


def test_linkify_keeps_query_parameters_intact():
    """Escaping first used to truncate or corrupt URLs carrying & or quotes."""
    out = linkify("https://example.com/r?a=1&b=2")
    assert 'href="https://example.com/r?a=1&amp;b=2"' in out


def test_linkify_drops_trailing_sentence_punctuation():
    out = linkify("see https://example.com/r.")
    assert 'href="https://example.com/r"' in out
    assert out.endswith(".")


def test_linkify_handles_several_links_in_one_item():
    out = linkify("[a](https://x.example) then https://y.example done")
    assert out.count("<a ") == 2
    assert "&lt;" not in out.replace("&lt;", "")  # no stray escaping artefacts
