# Slack Daily Review

## Context

Slack's Activity feed is not exposed by any API, so "my notifications" has to be
reconstructed. This tool produces one rolling markdown file summarizing everything that
wants my attention since the last run — mentions and DMs **verbatim**, threads
**summarized** since I last looked — and accepts my typed replies in that same file and
posts them back to Slack.

Every design question was settled empirically against a live two-account workspace; see
`docs/spike-findings.md`. Notable corrections that shaped this plan:

- **No Slack app to create, no admin approval.** The `slack@claude-plugins-official`
  plugin ships Slack's own registered OAuth client. One browser consent.
- **`to:me` is DM-only** — it does not find channel mentions, contradicting the plugin's
  own `slack-search` skill doc.
- **Mentions are findable only as a quoted exact phrase** on the raw markup
  `"<@Uxxx>"`. Unquoted fails; searching your handle fails worse (it matches the author
  field, so it returns everything you wrote).
- **Search hits are self-sufficient** — channel, author, ts, permalink, reply count all
  come back in one call. No enrichment pass, no hand-built permalinks.

## Decisions

| Decision | Choice |
|---|---|
| Slack access | Official plugin → `mcp.slack.com` (OAuth, no custom app) |
| Thread scope | Mentioned in **+** participated in |
| Trigger | Manual: `/slack-review` and `/slack-post` |
| File layout | Single rolling `INBOX.md` |
| Identity | `U0C2Y3CB0BX`, resolved at runtime, not hardcoded |

## The collector — three queries

```
mentions   keywords: ["\"<@ME>\""]   filters: -from:me   after: <since>
dms        filters: to:me            after: <since>
threads    filters: is:thread from:me     → slack_read_thread(oldest=last_seen)
```

That's the whole read path. No per-channel sweep.

## Architecture

```
slack-daily-review/
├── INBOX.md                  # the one file I read and type replies into
├── state/
│   ├── checkpoint.json       # last_run_ts, per-thread last_seen_ts
│   └── posted.log            # append-only audit of everything sent
├── scripts/
│   ├── slack_state.py        # window calc, checkpoint, thread registry
│   ├── inbox_parse.py        # INBOX.md -> pending replies JSON
│   └── inbox_write.py        # insert sections, mark replies sent
├── .claude/commands/
│   ├── slack-review.md       # /slack-review
│   └── slack-post.md         # /slack-post
└── docs/spike-findings.md
```

**Division of labor.** Scripts cannot call MCP tools — only the model can. So all Slack
I/O is model-driven, and scripts own exactly the deterministic local work: time windows,
checkpoint state, and reply parsing. That last one is a script specifically because a
model slip there posts your words to the wrong channel, irreversibly.

## INBOX.md format

HTML-comment anchors carry `channel`/`ts` invisibly so replies can be routed back.

```markdown
### mention · #general · Courtney · 12:48
<!-- item id=m-C0C34U44VDF-1789840108.623459 kind=mention channel=C0C34U44VDF ts=1789840108.623459 -->

> @jcounts can you confirm the migration window for Friday?

[open in Slack](https://…/archives/C0C34U44VDF/p1789840108623459)

<!-- reply id=m-C0C34U44VDF-1789840108.623459 status=draft -->
<!-- /reply -->
```

Type between the `reply` markers. Empty = skipped. After sending, `status=draft` becomes
`status=sent`, which makes `/slack-post` **idempotent** — running it twice never
double-posts.

Reply routing by kind: `mention` → threaded reply under that message; `dm` → the DM
channel, unthreaded; `thread` → into `thread_ts`.

## /slack-review

1. `slack_state.py window` → `since` (last run − 30 min overlap, or 24h on first run).
2. Run the three queries. Reproduce mentions and DMs **verbatim**; resolve `<@Uxxx|h>`
   to `@h`. Summarize thread deltas — what changed and what's being asked of me.
3. **Guard:** if the mentions query returns empty but the quoted-phrase trick is the only
   thing standing between us and silence, say so explicitly rather than reporting a
   clean "nothing today". The trick depends on undocumented tokenization.
4. `inbox_write.py insert` prepends a dated section, preserving existing open items and
   any drafts already typed.
5. `slack_state.py commit` — only after the write succeeds, so a crash can't skip a day.

## /slack-post

1. `inbox_parse.py` → pending replies as JSON.
2. Print a numbered dry-run: destination and exact text. **Confirm before sending.**
   `--dry-run` stops here.
3. Send via `slack_send_message`. Note messages are visibly tagged `*Sent using* Claude`
   in Slack — unavoidable.
4. `inbox_write.py mark-sent` + append to `posted.log`.
5. Register replied-to threads so follow-ups get summarized next run.

## Verification

- `inbox_parse.py` against a fixture `INBOX.md`: channel/ts recovery, empty drafts
  skipped, `status=sent` ignored.
- `/slack-review` in `App-testing` against the surviving `ZQFIXTURE` + CC messages.
- `/slack-post --dry-run`, then a real reply into the self-DM first.
- Idempotency: `/slack-post` twice → second run sends nothing.
- Checkpointing: `/slack-review` twice → no duplicate items.
