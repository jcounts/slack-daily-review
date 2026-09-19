#!/usr/bin/env python3
"""Assert that Slack search still behaves the way this tool depends on.

Why this exists
---------------
The collector rests on two behaviours that are NOT in Slack's documentation, and one
that actively contradicts it:

  1. Channel mentions are findable only as a QUOTED EXACT PHRASE on the raw markup
     `"<@Uxxx>"`. This depends on Slack's tokenizer and could change without notice.
  2. `to:me` matches DMs only and does NOT match channel mentions -- the opposite of
     what the Slack plugin's own `slack-search` skill documents.
  3. Keyword search matches the AUTHOR field, so searching your own handle returns
     everything you wrote rather than messages mentioning you.

If any of these shift, the tool does not crash. It quietly returns the wrong set --
usually an empty one, which looks exactly like a quiet day. That is the failure mode
this checker exists to make loud.

Scripts cannot call MCP tools, so this does not talk to Slack. The model runs the live
queries (see /slack-selftest) and hands the raw output here as an evidence file.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = ROOT / "tests" / "fixtures" / "workspace_contract.json"

TS_RE = re.compile(r"Message_ts:\s*(\d+\.\d+)")
PERMALINK_TS_RE = re.compile(r"/p(\d{10})(\d{6})\b")

FAIL, CHANGED, OK, UNKNOWN = "FAIL", "CHANGED", "OK", "UNKNOWN"


def extract_ts(blob: str) -> set[str]:
    """Pull message timestamps out of a raw search result blob.

    Handles both the `Message_ts: 123.456` field and the `/p123456789012345` form
    embedded in permalinks, so it works whether or not the caller used
    response_format="detailed".
    """
    found = set(TS_RE.findall(blob or ""))
    found |= {f"{a}.{b}" for a, b in PERMALINK_TS_RE.findall(blob or "")}
    return found


# name, evidence key, relation, fixture message key, severity, explanation on failure
CHECKS = [
    ("mention_query_finds_partner_mention", "mentions", "contains", "mention_by_partner", FAIL,
     "The quoted-phrase mention trick has STOPPED WORKING. `keywords: ['\"<@ME>\"']` no "
     "longer matches a known mention. /slack-review will report quiet days that are not "
     "quiet. Switch to the per-channel fallback: slack_list_user_channels + "
     "slack_read_channel(oldest=...) filtered locally for '<@ME'."),

    ("mention_query_excludes_control", "mentions", "excludes", "control_no_mention", FAIL,
     "The mention query is OVER-matching: it returned a message containing no mention at "
     "all. Most likely the quoted phrase is being tokenized loosely. The digest will fill "
     "with noise."),

    ("mention_query_excludes_own_messages", "mentions", "excludes", "mention_by_self", FAIL,
     "`-from:me` is no longer excluding your own messages, so you will be shown your own "
     "mentions of yourself."),

    ("dm_query_finds_partner_dm", "dms", "contains", "dm_from_partner", FAIL,
     "`to:me` no longer returns a known inbound DM. DMs will silently vanish from the "
     "digest."),

    ("dm_query_excludes_channel_mention", "dms", "excludes", "mention_by_partner", CHANGED,
     "`to:me` has STARTED matching channel mentions. This contradicts what was measured "
     "and may mean the design can be simplified to a single query -- but until that is "
     "re-verified, mentions will now appear twice in the digest."),

    ("author_field_trap_still_present", "author_trap", "empty", None, CHANGED,
     "Searching the bare handle from another author used to return nothing (proving "
     "keyword search does not match mention markup). It now returns results, so the "
     "tokenizer changed -- re-check whether a simpler mention query is possible."),
]


def evaluate(evidence: dict, contract: dict) -> list[dict]:
    msgs = contract["messages"]
    results = []
    for name, key, relation, msg_key, severity, explain in CHECKS:
        blob = evidence.get(key)
        if blob is None:
            results.append({"check": name, "status": UNKNOWN,
                            "detail": f"no evidence supplied for '{key}'"})
            continue

        found = extract_ts(blob)
        target = msgs.get(msg_key) if msg_key else None

        if relation == "contains":
            ok = target in found
        elif relation == "excludes":
            ok = target not in found
        elif relation == "empty":
            ok = not found
        else:
            raise ValueError(f"unknown relation {relation!r}")

        if ok:
            results.append({"check": name, "status": OK, "detail": ""})
        else:
            results.append({
                "check": name,
                "status": severity,
                "detail": explain,
                "expected": f"{relation} {target}" if target else relation,
                "found_ts": sorted(found),
            })
    return results


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--evidence", type=Path, required=True,
                   help="JSON file: {'mentions': '<raw>', 'dms': '<raw>', 'author_trap': '<raw>'}")
    p.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args()

    evidence = json.loads(args.evidence.read_text())
    contract = json.loads(args.contract.read_text())
    results = evaluate(evidence, contract)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"[{r['status']:7}] {r['check']}")
            if r["detail"]:
                print(f"          {r['detail']}")
                if r.get("found_ts"):
                    print(f"          timestamps returned: {r['found_ts']}")

    statuses = {r["status"] for r in results}
    if FAIL in statuses:
        print("\nCONTRACT BROKEN -- /slack-review cannot be trusted until this is fixed.",
              file=sys.stderr)
        return 1
    if CHANGED in statuses:
        print("\nSlack behaviour CHANGED. Nothing is broken, but re-verify the design.",
              file=sys.stderr)
        return 2
    if UNKNOWN in statuses:
        print("\nIncomplete evidence -- some checks did not run.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
