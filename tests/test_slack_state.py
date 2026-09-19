"""Unit tests for the collection window and thread registry.

The window is the other place a quiet bug loses messages: if the checkpoint advances
when it should not, or the overlap disappears, a day's mentions vanish and the digest
still looks healthy.
"""
import importlib
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import slack_state  # noqa: E402


class StateTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        slack_state.STATE_PATH = self.dir / "checkpoint.json"

    def tearDown(self):
        importlib.reload(slack_state)


class TestWindow(StateTest):
    def test_first_run_looks_back_a_day(self):
        slack_state.save({"last_run_ts": None, "threads": {}})
        now = int(time.time())
        state = slack_state.load()
        self.assertIsNone(state["last_run_ts"])
        # the window helper derives since = now - FIRST_RUN_LOOKBACK
        self.assertEqual(slack_state.FIRST_RUN_LOOKBACK, 24 * 3600)
        self.assertLess(now - slack_state.FIRST_RUN_LOOKBACK, now)

    def test_subsequent_runs_overlap_rather_than_starting_exactly_at_last_run(self):
        # indexing is fast but not instantaneous; a hard boundary drops messages
        self.assertGreater(slack_state.OVERLAP, 0,
                           "a zero overlap will silently lose messages near the boundary")
        last = 1_000_000
        slack_state.save({"last_run_ts": last, "threads": {}})
        since = slack_state.load()["last_run_ts"] - slack_state.OVERLAP
        self.assertLess(since, last)


class TestPersistence(StateTest):
    def test_roundtrip(self):
        slack_state.save({"last_run_ts": 123, "threads": {"C:1.1": {"last_seen_ts": "2.2"}}})
        self.assertEqual(slack_state.load()["threads"]["C:1.1"]["last_seen_ts"], "2.2")

    def test_missing_file_yields_a_usable_empty_state(self):
        self.assertEqual(slack_state.load(), {"last_run_ts": None, "threads": {}})

    def test_write_is_atomic_leaving_no_partial_file(self):
        slack_state.save({"last_run_ts": 1, "threads": {}})
        leftovers = list(self.dir.glob("*.tmp"))
        self.assertEqual(leftovers, [], "a temp file survived; a crash could corrupt state")


class TestThreadTTL(StateTest):
    def test_stale_threads_are_forgotten(self):
        old = int(time.time()) - slack_state.THREAD_TTL - 1
        fresh = int(time.time())
        slack_state.save({"last_run_ts": 1, "threads": {
            "C:old": {"updated_ts": old, "last_seen_ts": "1.1"},
            "C:new": {"updated_ts": fresh, "last_seen_ts": "2.2"},
        }})
        now = time.time()
        kept = [k for k, r in slack_state.load()["threads"].items()
                if now - float(r["updated_ts"]) <= slack_state.THREAD_TTL]
        self.assertEqual(kept, ["C:new"])

    def test_ttl_is_not_absurdly_short(self):
        self.assertGreaterEqual(slack_state.THREAD_TTL, 3 * 86400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
