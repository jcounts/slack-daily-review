---
description: Verify Slack's search still behaves the way slack-daily-review depends on
---

Check the undocumented Slack behaviours this tool rests on. Run this when
`/slack-review` reports a suspiciously quiet day, or periodically as a canary.

Requires the `App-testing` workspace with its fixture messages intact
(`tests/fixtures/workspace_contract.json` lists the expected message timestamps).
Read that file first for `me`, `partner`, and the fixture ids.

## 1. Offline tests

```
./run-tests.sh
```

These cover the parser, routing and state logic. If they fail, stop — the local code is
broken and the live results would be meaningless.

## 2. Three live probes

Run each with `include_context: false` and the **default** `response_format`
(`"detailed"`), because the checker needs `Message_ts` or permalinks. Capture the raw
result text of each verbatim.

| Probe | Call |
|---|---|
| `mentions` | `slack_search_public_and_private(keywords: ["\"<@<ME>>\""], filters: "-from:me")` |
| `dms` | `slack_search_public_and_private(filters: "to:me", keywords: [])` |
| `author_trap` | `slack_search_public_and_private(keywords: ["<my handle>"], filters: "from:<@<PARTNER>>")` |

Do not add date filters — the fixtures are old and would be excluded.

The third probe is the control: it must return **nothing**. It confirms keyword search
still fails to match mention markup, which is why the quoted-phrase form is necessary.

## 3. Evaluate

Write the three raw blobs into a JSON evidence file in your scratchpad:

```json
{"mentions": "<raw>", "dms": "<raw>", "author_trap": "<raw>"}
```

```
python3 scripts/check_slack_contract.py --evidence <file>
```

## 4. Report

Exit codes: `0` all good · `1` **contract broken** · `2` behaviour changed but not broken
· `3` incomplete evidence.

- **On 1**, say plainly that `/slack-review` cannot be trusted until it is fixed, and
  quote the checker's explanation — it names the fallback to switch to.
- **On 2**, report what changed. A `to:me` that starts matching channel mentions would
  be an improvement, but it double-reports until the design is revisited.
- **On 3**, do not report success. Say which probe produced no evidence.

Never summarise a failing run as "mostly fine". A silent contract break looks exactly
like a quiet day, which is the whole reason this command exists.
