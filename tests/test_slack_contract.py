"""Unit tests for the Slack search contract checker.

These do not touch Slack. They feed the checker synthetic search output representing
each way the undocumented behaviour could regress, and assert the checker notices.
The point is that a silent behaviour change becomes a loud test failure.
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_slack_contract import (  # noqa: E402
    CHANGED, FAIL, OK, UNKNOWN, evaluate, extract_ts,
)

CONTRACT = json.loads((ROOT / "tests" / "fixtures" / "workspace_contract.json").read_text())
M = CONTRACT["messages"]


def hit(ts: str, text: str = "some message") -> str:
    """A single search result in the shape Slack's MCP actually returns."""
    return (
        f"Channel: #general (ID: C0C34U44VDF)\n"
        f"From: Courtney <x@y.com> (ID: U0C2Y8980GM)\n"
        f"Message_ts: {ts}\n"
        f"Permalink: [link](https://apptesting-9pl4296.slack.com/archives/C0C34U44VDF/p{ts.replace('.', '')})\n"
        f"Text: \n{text}\n---\n"
    )


def status_of(results, name):
    return next(r["status"] for r in results if r["check"] == name)


HEALTHY = {
    "mentions": hit(M["mention_by_partner"], "<@U0C2Y3CB0BX|jcounts> ping"),
    "dms": hit(M["dm_from_partner"], "hey bruh"),
    "author_trap": "No results found.",
}


class TestExtractTs(unittest.TestCase):
    def test_reads_message_ts_field(self):
        self.assertEqual(extract_ts("Message_ts: 1789840108.623459"), {"1789840108.623459"})

    def test_reads_ts_from_permalink_when_field_absent(self):
        # concise responses omit Message_ts but permalinks still carry it
        blob = "Permalink: [link](https://x.slack.com/archives/C1/p1789840108623459)"
        self.assertEqual(extract_ts(blob), {"1789840108.623459"})

    def test_empty_blob_yields_nothing(self):
        self.assertEqual(extract_ts(""), set())
        self.assertEqual(extract_ts("No results found."), set())

    def test_does_not_confuse_other_numbers(self):
        self.assertEqual(extract_ts("Reply count: 2\nlimit 20"), set())


class TestHealthyContract(unittest.TestCase):
    def test_everything_passes_when_slack_behaves(self):
        results = evaluate(HEALTHY, CONTRACT)
        self.assertTrue(all(r["status"] == OK for r in results),
                        msg=f"unexpected non-OK: {[r for r in results if r['status'] != OK]}")


class TestMentionTrickRegressions(unittest.TestCase):
    """The headline risk: the quoted-phrase mention trick silently stops matching."""

    def test_empty_mention_results_is_a_hard_failure(self):
        ev = dict(HEALTHY, mentions="No results found.")
        results = evaluate(ev, CONTRACT)
        self.assertEqual(status_of(results, "mention_query_finds_partner_mention"), FAIL)

    def test_failure_explains_the_fallback(self):
        ev = dict(HEALTHY, mentions="No results found.")
        r = next(x for x in evaluate(ev, CONTRACT)
                 if x["check"] == "mention_query_finds_partner_mention")
        self.assertIn("slack_read_channel", r["detail"],
                      "a broken-contract message must name the fallback, not just complain")

    def test_over_matching_control_message_is_a_hard_failure(self):
        # the tokenizer loosening so a no-mention message matches
        ev = dict(HEALTHY, mentions=HEALTHY["mentions"] + hit(M["control_no_mention"], "no mention"))
        results = evaluate(ev, CONTRACT)
        self.assertEqual(status_of(results, "mention_query_excludes_control"), FAIL)

    def test_self_authored_mention_leaking_through_is_a_hard_failure(self):
        # -from:me quietly ceasing to filter
        ev = dict(HEALTHY, mentions=HEALTHY["mentions"] + hit(M["mention_by_self"], "self ping"))
        results = evaluate(ev, CONTRACT)
        self.assertEqual(status_of(results, "mention_query_excludes_own_messages"), FAIL)


class TestToMeRegressions(unittest.TestCase):
    """`to:me` is DM-only today, which contradicts the plugin's own skill doc."""

    def test_missing_dm_is_a_hard_failure(self):
        ev = dict(HEALTHY, dms="No results found.")
        results = evaluate(ev, CONTRACT)
        self.assertEqual(status_of(results, "dm_query_finds_partner_dm"), FAIL)

    def test_to_me_gaining_channel_mentions_is_flagged_as_changed_not_broken(self):
        # an improvement, but it would double-report mentions until the design is revisited
        ev = dict(HEALTHY, dms=HEALTHY["dms"] + hit(M["mention_by_partner"], "<@U0C2Y3CB0BX> ping"))
        results = evaluate(ev, CONTRACT)
        self.assertEqual(status_of(results, "dm_query_excludes_channel_mention"), CHANGED)


class TestAuthorFieldTrap(unittest.TestCase):
    def test_trap_present_is_ok(self):
        self.assertEqual(status_of(evaluate(HEALTHY, CONTRACT),
                                   "author_field_trap_still_present"), OK)

    def test_trap_disappearing_is_flagged_as_changed(self):
        ev = dict(HEALTHY, author_trap=hit(M["mention_by_partner"]))
        results = evaluate(ev, CONTRACT)
        self.assertEqual(status_of(results, "author_field_trap_still_present"), CHANGED)


class TestIncompleteEvidence(unittest.TestCase):
    def test_missing_evidence_is_unknown_not_silently_ok(self):
        results = evaluate({"mentions": HEALTHY["mentions"]}, CONTRACT)
        self.assertEqual(status_of(results, "dm_query_finds_partner_dm"), UNKNOWN)

    def test_no_evidence_at_all_never_reports_ok(self):
        results = evaluate({}, CONTRACT)
        self.assertTrue(all(r["status"] == UNKNOWN for r in results),
                        "an empty evidence file must not look like a passing run")


if __name__ == "__main__":
    unittest.main(verbosity=2)
