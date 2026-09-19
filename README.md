# slack-daily-review

A daily Slack catch-up that writes to a file you can reply in.

`/slack-review` collects what wants your attention since the last run and prepends it to
`INBOX.md`: **mentions and DMs verbatim**, **threads summarized** since you last looked.
You type replies inline. `/slack-post` sends them.

## Setup

```bash
/plugin install slack@claude-plugins-official   # ships Slack's own OAuth client
```

Then authenticate once in the browser. No custom Slack app and no admin approval are
needed — the plugin carries a registered first-party client id.

## Use

```
/slack-review              # collect into INBOX.md
# ...open INBOX.md, type between the `reply` markers...
/slack-post --dry-run      # see exactly what would go where
/slack-post                # send, after confirming
/slack-post --draft        # create Slack drafts instead of sending
```

An empty reply block is skipped. Sent replies flip to `status=sent`, so running
`/slack-post` twice never double-posts.

## How it works

Three search queries are the entire read path — no per-channel sweep:

| Need | Query |
|---|---|
| Channel mentions | `keywords: ["\"<@ME>\""]` + `filters: -from:me` |
| DMs & group DMs | `filters: to:me` |
| Thread deltas | `filters: is:thread from:me` → `slack_read_thread(oldest=…)` |

Scripts cannot call MCP tools, so all Slack I/O is model-driven. `scripts/` owns only the
deterministic local work: the collection window, the checkpoint, and reply parsing — that
last one is a script specifically because a mistake there posts your words to the wrong
channel, irreversibly.

## Things that will bite you

- **`to:me` does not find channel mentions.** It is DM-only. The Slack plugin's own
  `slack-search` skill documents otherwise; it is wrong. The tool schema is right.
- **Mentions are findable only as a quoted exact phrase** on the raw markup `"<@U...>"`.
  Unquoted fails. Searching your handle fails worse — keyword search matches the *author*
  field, so it returns everything you wrote.
- That trick relies on undocumented tokenization, so `/slack-review` sanity-checks it and
  complains loudly rather than reporting a falsely quiet day.
- **Messages posted through this MCP are tagged "Sent using Claude" in Slack.** Visible to
  recipients, unavoidable.
- There is no read-state API. "Notifications" is approximated by a time window plus a local
  checkpoint (with 30 min overlap and id-based dedup), never by Slack's actual unreads.

## Tests

```bash
./run-tests.sh      # 39 offline unit tests; never touch Slack
/slack-selftest     # live canary against Slack's actual search behaviour
```

The offline suite covers reply routing (mention → in-thread, DM → unthreaded, thread →
parent ts), the refusals that matter (`sent` skipped, empty skipped, orphan reported
rather than guessed at), body fidelity, and the window/TTL logic.

`/slack-selftest` is the one that guards the caveats above. The quoted-mention trick and
`to:me`'s DM-only behaviour live in Slack's remote service, not in this repo, so they
cannot be unit tested — but their failure mode is an empty result set, which is
indistinguishable from a quiet day. The canary runs the real queries against known
fixture messages and fails loudly, naming the fallback to switch to. Its assertion logic
*is* unit tested, against synthetic output simulating each way the behaviour could break.

Full empirical notes: `docs/spike-findings.md`. Design: `PLAN.md`.
