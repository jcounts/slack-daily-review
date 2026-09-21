#!/usr/bin/env python3
"""Extract pending replies from INBOX.md as JSON.

This is a script rather than model work on purpose: it maps typed prose back to a
channel id and timestamp, and getting that wrong means posting your words into the
wrong conversation, irreversibly. Deterministic parsing, no inference.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from paths import inbox_path

DEFAULT_INBOX = inbox_path()

ITEM_RE = re.compile(r"<!--\s*item\s+(?P<attrs>[^>]*?)-->")
REPLY_RE = re.compile(
    r"<!--\s*reply\s+(?P<attrs>[^>]*?)-->(?P<body>.*?)<!--\s*/reply\s*-->",
    re.DOTALL,
)
ATTR_RE = re.compile(r"(\w+)=([^\s>]+)")
COMMENT_LINE_RE = re.compile(r"^\s*<!--.*?-->\s*$")


def parse_attrs(raw: str) -> dict:
    return dict(ATTR_RE.findall(raw))


def clean_body(body: str) -> str:
    """Strip comment lines and surrounding blank space; keep the author's text as-is."""
    lines = [ln for ln in body.splitlines() if not COMMENT_LINE_RE.match(ln)]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def route(kind: str, item: dict) -> str | None:
    """Where a reply to this item should go.

    mention -> threaded reply under the mentioning message, so it lands in context
               rather than as a loose channel post
    thread  -> into the existing thread
    dm      -> the DM channel itself, unthreaded
    """
    if kind == "mention":
        return item.get("ts")
    if kind == "thread":
        return item.get("thread_ts")
    return None


def parse(text: str) -> tuple[list[dict], list[dict]]:
    items = {a["id"]: a for a in (parse_attrs(m.group("attrs")) for m in ITEM_RE.finditer(text)) if "id" in a}

    pending, problems = [], []
    for m in REPLY_RE.finditer(text):
        attrs = parse_attrs(m.group("attrs"))
        rid = attrs.get("id")
        status = attrs.get("status", "draft")
        body = clean_body(m.group("body"))

        if not rid:
            problems.append({"error": "reply block with no id", "at": m.start()})
            continue
        if status != "draft":
            continue          # already sent; skip -- this is what makes posting idempotent
        if not body:
            continue          # empty draft = deliberately skipped

        item = items.get(rid)
        if item is None:
            problems.append({"id": rid, "error": "no matching item anchor"})
            continue
        channel = item.get("channel")
        if not channel:
            problems.append({"id": rid, "error": "item anchor has no channel"})
            continue

        pending.append({
            "id": rid,
            "kind": item.get("kind", "unknown"),
            "channel": channel,
            "ts": item.get("ts"),
            "thread_ts": route(item.get("kind", ""), item),
            "text": body,
        })
    return pending, problems


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    p.add_argument("--existing-ids", action="store_true",
                   help="print the item ids already in the file, one per line, and exit. "
                        "Used by /slack-daily-review:slack-review to skip items it has already recorded, "
                        "since the collection window deliberately overlaps.")
    args = p.parse_args()

    if args.existing_ids:
        if not args.inbox.exists():
            return 0
        text = args.inbox.read_text()
        for m in ITEM_RE.finditer(text):
            attrs = parse_attrs(m.group("attrs"))
            if "id" in attrs:
                print(attrs["id"])
        return 0

    if not args.inbox.exists():
        print(json.dumps({"pending": [], "problems": [
            {"error": f"no such file: {args.inbox}"}]}, indent=2))
        return 1

    pending, problems = parse(args.inbox.read_text())
    print(json.dumps({"pending": pending, "problems": problems,
                      "count": len(pending)}, indent=2))
    # Non-zero only on malformed input, so a caller can distinguish "nothing to do"
    # from "the file is broken".
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
