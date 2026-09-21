#!/usr/bin/env python3
"""Mutate INBOX.md: create it, prepend a new review section, mark replies sent.

All edits are anchored to HTML comments so hand-typed prose is never disturbed.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from paths import inbox_path

DEFAULT_INBOX = inbox_path()

FEED_START = "<!-- feed:start -->"
LAST_REVIEW_RE = re.compile(r"^_Last review: .*_$", re.MULTILINE)

SKELETON = f"""# Slack Inbox

<!-- slack-inbox v1 -->

_Last review: never_

Type replies between the `reply` markers under any item, then run
`/slack-daily-review:slack-post`.
An empty reply block is skipped. Sent replies are marked `status=sent` and will not
be sent again.

{FEED_START}
<!-- feed:end -->
"""


def cmd_init(args) -> None:
    if args.inbox.exists() and not args.force:
        print(f"{args.inbox} already exists (use --force to overwrite)")
        return
    args.inbox.write_text(SKELETON)
    print(f"created {args.inbox}")


def cmd_insert(args) -> None:
    if not args.inbox.exists():
        args.inbox.write_text(SKELETON)

    text = args.inbox.read_text()
    if FEED_START not in text:
        raise SystemExit(f"{args.inbox} is missing {FEED_START}; cannot insert safely")

    content = args.content_file.read_text().rstrip() + "\n"

    # Newest first: everything new goes directly under the feed marker, so existing
    # items and any drafts already typed below are untouched.
    text = text.replace(FEED_START, FEED_START + "\n\n" + content, 1)

    stamp = args.last_review or time.strftime("%Y-%m-%d %H:%M %Z")
    replacement = f"_Last review: {stamp}_"
    if LAST_REVIEW_RE.search(text):
        text = LAST_REVIEW_RE.sub(replacement, text, count=1)

    args.inbox.write_text(text)
    print(f"inserted {len(content.splitlines())} lines into {args.inbox}")


def cmd_mark_sent(args) -> None:
    text = args.inbox.read_text()
    pattern = re.compile(
        r"<!--\s*reply\s+id=" + re.escape(args.id) + r"\s+status=draft[^>]*?-->"
    )
    if not pattern.search(text):
        raise SystemExit(f"no draft reply block found for id={args.id}")

    bits = [f"id={args.id}", "status=sent"]
    if args.ts:
        bits.append(f"at={args.ts}")
    if args.permalink:
        bits.append(f"permalink={args.permalink}")
    new = "<!-- reply " + " ".join(bits) + " -->"

    args.inbox.write_text(pattern.sub(new, text, count=1))
    print(f"marked {args.id} as sent")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="create the INBOX.md skeleton")
    i.add_argument("--force", action="store_true")
    i.set_defaults(func=cmd_init)

    n = sub.add_parser("insert", help="prepend a new review section")
    n.add_argument("--content-file", type=Path, required=True, dest="content_file")
    n.add_argument("--last-review", default=None, dest="last_review")
    n.set_defaults(func=cmd_insert)

    m = sub.add_parser("mark-sent", help="flip a reply block from draft to sent")
    m.add_argument("--id", required=True)
    m.add_argument("--ts", default=None)
    m.add_argument("--permalink", default=None)
    m.set_defaults(func=cmd_mark_sent)

    args = p.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
