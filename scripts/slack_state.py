#!/usr/bin/env python3
"""Local state for slack-daily-review.

This script never talks to Slack -- scripts cannot call MCP tools, only the model
can. Its whole job is the deterministic bookkeeping the model should not improvise:
the collection window and the per-thread "last seen" marks.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "checkpoint.json"

FIRST_RUN_LOOKBACK = 24 * 3600   # how far back to look when there is no checkpoint
OVERLAP = 30 * 60                # re-scan this much before last_run; search indexing
                                 # is fast but not instantaneous, and duplicates are
                                 # cheaper to drop than missed messages are to notice
THREAD_TTL = 7 * 86400           # forget threads with no activity for this long


def load() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"last_run_ts": None, "threads": {}}


def save(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(STATE_PATH)  # atomic: a crash mid-write cannot corrupt the checkpoint


def cmd_window(args) -> None:
    state = load()
    now = int(time.time())
    last = state.get("last_run_ts")
    if last is None:
        since = now - FIRST_RUN_LOOKBACK
        basis = "first-run"
    else:
        since = int(last) - OVERLAP
        basis = "last-run-minus-overlap"
    print(json.dumps({
        "since_ts": since,
        "since_date": time.strftime("%Y-%m-%d", time.localtime(since)),
        "since_human": time.strftime("%Y-%m-%d %H:%M %Z", time.localtime(since)),
        "now_ts": now,
        "basis": basis,
        "last_run_ts": last,
    }, indent=2))


def cmd_commit(args) -> None:
    state = load()
    state["last_run_ts"] = int(args.now or time.time())
    save(state)
    print(f"checkpoint committed: last_run_ts={state['last_run_ts']}")


def _key(channel: str, thread_ts: str) -> str:
    return f"{channel}:{thread_ts}"


def cmd_thread_list(args) -> None:
    state = load()
    now = time.time()
    out = []
    for key, rec in sorted(state.get("threads", {}).items()):
        if now - float(rec.get("updated_ts", 0)) > THREAD_TTL:
            continue
        channel, thread_ts = key.split(":", 1)
        out.append({
            "channel": channel,
            "thread_ts": thread_ts,
            "last_seen_ts": rec.get("last_seen_ts"),
            "title": rec.get("title", ""),
        })
    print(json.dumps(out, indent=2))


def cmd_thread_seen(args) -> None:
    """Register a thread and/or advance its last-seen mark."""
    state = load()
    threads = state.setdefault("threads", {})
    rec = threads.setdefault(_key(args.channel, args.thread_ts), {})
    if args.last_seen:
        rec["last_seen_ts"] = args.last_seen
    if args.title:
        rec["title"] = args.title
    rec["updated_ts"] = int(time.time())
    save(state)
    print(f"thread {args.channel}:{args.thread_ts} last_seen={rec.get('last_seen_ts')}")


def cmd_thread_prune(args) -> None:
    state = load()
    now = time.time()
    threads = state.get("threads", {})
    dropped = [k for k, r in threads.items()
               if now - float(r.get("updated_ts", 0)) > THREAD_TTL]
    for k in dropped:
        del threads[k]
    save(state)
    print(f"pruned {len(dropped)} stale thread(s)")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("window", help="print the collection window as JSON").set_defaults(func=cmd_window)

    c = sub.add_parser("commit", help="record that a review completed")
    c.add_argument("--now", type=int, default=None)
    c.set_defaults(func=cmd_commit)

    sub.add_parser("thread-list", help="active watched threads").set_defaults(func=cmd_thread_list)

    t = sub.add_parser("thread-seen", help="register a thread / advance last-seen")
    t.add_argument("--channel", required=True)
    t.add_argument("--thread-ts", required=True, dest="thread_ts")
    t.add_argument("--last-seen", dest="last_seen", default=None)
    t.add_argument("--title", default=None)
    t.set_defaults(func=cmd_thread_seen)

    sub.add_parser("thread-prune", help="drop threads idle past the TTL").set_defaults(func=cmd_thread_prune)

    args = p.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
