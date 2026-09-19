"""Unit tests for the INBOX.md reply round-trip.

This is the other place a silent bug is expensive: the parser maps typed prose back to
a channel id and timestamp, and getting that wrong posts your words into the wrong
conversation, with no undo. These tests pin the routing rules and the idempotency
guarantee that stops /slack-post double-sending.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from inbox_parse import clean_body, parse, route  # noqa: E402

PARSE = ROOT / "scripts" / "inbox_parse.py"
WRITE = ROOT / "scripts" / "inbox_write.py"


def doc(*blocks: str) -> str:
    return "# Slack Inbox\n<!-- feed:start -->\n" + "\n".join(blocks) + "\n<!-- feed:end -->\n"


def item(kind, cid, ts, thread_ts=None, body="draft text", status="draft"):
    rid = f"{kind[0]}-{cid}-{ts}"
    extra = f" thread_ts={thread_ts}" if thread_ts else ""
    return (
        f"### {kind}\n"
        f"<!-- item id={rid} kind={kind} channel={cid} ts={ts}{extra} -->\n\n"
        f"> quoted\n\n"
        f"<!-- reply id={rid} status={status} -->\n{body}\n<!-- /reply -->\n"
    )


class TestRouting(unittest.TestCase):
    """Where a reply is sent is derived, never guessed."""

    def test_mention_replies_in_thread_under_the_mentioning_message(self):
        # not a loose channel post -- it must land in context
        self.assertEqual(route("mention", {"ts": "111.1"}), "111.1")

    def test_dm_reply_is_unthreaded(self):
        self.assertIsNone(route("dm", {"ts": "222.2"}))

    def test_thread_reply_targets_the_parent_not_the_newest_message(self):
        # the item ts is the newest reply; posting to that would start a nested thread
        self.assertEqual(route("thread", {"ts": "999.9", "thread_ts": "333.3"}), "333.3")

    def test_unknown_kind_is_unthreaded_rather_than_misrouted(self):
        self.assertIsNone(route("something-new", {"ts": "444.4"}))

    def test_end_to_end_routing_through_the_parser(self):
        pending, problems = parse(doc(
            item("mention", "C1", "111.1"),
            item("dm", "D1", "222.2"),
            item("thread", "C2", "999.9", thread_ts="333.3"),
        ))
        self.assertEqual(problems, [])
        self.assertEqual(
            {p["id"]: p["thread_ts"] for p in pending},
            {"m-C1-111.1": "111.1", "d-D1-222.2": None, "t-C2-999.9": "333.3"},
        )


class TestWhatIsNotSent(unittest.TestCase):
    def test_already_sent_blocks_are_skipped(self):
        pending, _ = parse(doc(item("mention", "C1", "111.1", status="sent")))
        self.assertEqual(pending, [])

    def test_empty_draft_is_skipped_not_sent_blank(self):
        pending, _ = parse(doc(item("mention", "C1", "111.1", body="   \n\n")))
        self.assertEqual(pending, [])

    def test_orphan_reply_is_reported_never_sent(self):
        # no item anchor means no known destination; guessing would be unsafe
        pending, problems = parse(doc(
            "<!-- reply id=ORPHAN status=draft -->\ntext\n<!-- /reply -->"))
        self.assertEqual(pending, [])
        self.assertEqual(problems[0]["id"], "ORPHAN")

    def test_item_without_channel_is_reported_never_sent(self):
        pending, problems = parse(doc(
            "<!-- item id=X kind=mention ts=1.1 -->\n"
            "<!-- reply id=X status=draft -->\ntext\n<!-- /reply -->"))
        self.assertEqual(pending, [])
        self.assertIn("channel", problems[0]["error"])


class TestBodyFidelity(unittest.TestCase):
    """The user's text is sent verbatim; only our own scaffolding is stripped."""

    def test_comment_scaffolding_is_removed(self):
        self.assertEqual(clean_body("\n<!-- hint -->\nreal text\n\n"), "real text")

    def test_internal_blank_lines_and_markdown_survive(self):
        body = "para one\n\n- bullet\n- bullet\n\n`code`"
        self.assertEqual(clean_body(f"\n{body}\n"), body)

    def test_text_is_not_reflowed_or_trimmed_internally(self):
        body = "line with  double  spaces\n    indented continuation"
        self.assertEqual(clean_body(body), body)


class TestIdempotency(unittest.TestCase):
    """Running /slack-post twice must never double-post."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "INBOX.md"
        self.tmp.write_text(doc(item("mention", "C1", "111.1")))

    def run_script(self, script, *args):
        return subprocess.run([sys.executable, str(script), "--inbox", str(self.tmp), *args],
                              capture_output=True, text=True)

    def pending_count(self):
        out = subprocess.run([sys.executable, str(PARSE), "--inbox", str(self.tmp)],
                             capture_output=True, text=True).stdout
        return json.loads(out)["count"]

    def test_marking_sent_removes_it_from_the_pending_set(self):
        self.assertEqual(self.pending_count(), 1)
        self.run_script(WRITE, "mark-sent", "--id", "m-C1-111.1", "--ts", "9.9")
        self.assertEqual(self.pending_count(), 0)

    def test_marking_the_same_reply_twice_fails_loudly(self):
        self.run_script(WRITE, "mark-sent", "--id", "m-C1-111.1", "--ts", "9.9")
        second = self.run_script(WRITE, "mark-sent", "--id", "m-C1-111.1", "--ts", "9.9")
        self.assertNotEqual(second.returncode, 0)

    def test_mark_sent_records_permalink_for_the_audit_trail(self):
        self.run_script(WRITE, "mark-sent", "--id", "m-C1-111.1",
                        "--ts", "9.9", "--permalink", "https://x/y")
        self.assertIn("permalink=https://x/y", self.tmp.read_text())

    def test_insert_preserves_drafts_already_typed_below(self):
        subprocess.run([sys.executable, str(WRITE), "--inbox", str(self.tmp),
                        "insert", "--content-file", "/dev/stdin"],
                       input="## new day\n", capture_output=True, text=True)
        text = self.tmp.read_text()
        self.assertIn("## new day", text)
        self.assertIn("m-C1-111.1", text)          # the old item survived
        self.assertEqual(self.pending_count(), 1)  # and its draft is still sendable

    def test_existing_ids_lists_everything_for_dedup(self):
        out = subprocess.run([sys.executable, str(PARSE), "--inbox", str(self.tmp),
                              "--existing-ids"], capture_output=True, text=True).stdout
        self.assertEqual(out.split(), ["m-C1-111.1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
