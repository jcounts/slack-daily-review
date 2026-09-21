---
description: Collect Slack mentions, DMs and thread updates since the last review into INBOX.md
disable-model-invocation: true
---

Build today's Slack review and prepend it to the inbox file.

## 0. Setup

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" window` and use `since_ts` /
`since_date` below.

The inbox and checkpoint live outside the plugin (default `~/.slack-daily-review/`, or
`$SLACK_DAILY_REVIEW_HOME`); the scripts resolve that themselves. Never construct those
paths by hand — a plugin update replaces this directory, so anything written inside it is
lost.

Get **my own user id** from any `slack_search_*` tool description — they state
"Current logged in user's user_id is `U...`". Call it `<ME>`. Never hardcode it; it
changes with the authenticated workspace.

## 1. Mentions in channels — verbatim

```
slack_search_public_and_private(
  keywords: ["\"<@<ME>>\""],          # quoted exact phrase; see the warning below
  filters:  "-from:me after:<since_date>",
  sort: "timestamp", sort_dir: "desc",
  include_context: false
)
```

**Why it looks like that.** Mention markup is only findable as a *quoted exact phrase* on
the bare form `"<@U...>"`. Do not "simplify" this:

- unquoted `<@U...>` does not reliably match
- searching my handle (`jcounts`) matches the **author** field, so it returns everything
  *I* wrote, including messages containing no mention at all
- `to:me` does **not** find channel mentions — it is DM-only

**Guard.** This relies on undocumented tokenization. If this query returns zero results,
do not silently report a quiet day. Sanity-check with a bare keyword search for any
recent word in a channel you know is active; if that returns hits while the mention query
returns none, the trick has regressed — say so prominently at the top of the review and
fall back to `slack_list_user_channels` + `slack_read_channel(oldest=since_ts)` per
channel, filtering locally for `<@<ME>`.

## 2. DMs and group DMs — verbatim

```
slack_search_public_and_private(
  filters: "to:me", keywords: [], after: "<since_ts>",
  sort: "timestamp", include_context: false
)
```

Paginate with `cursor` while `pagination_info` offers more (`limit` caps at 20).

## 3. Threads — summarized

Discover threads I'm in:

```
slack_search_public_and_private(filters: "is:thread from:me", keywords: [], include_context: false)
```

Merge with `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" thread-list`, plus the
`thread_ts` of any mention from step 1 that sits in a thread (a reply's permalink carries
`?thread_ts=`).

For each thread, fetch only the delta:

```
slack_read_thread(channel_id, message_ts: <parent ts>, oldest: <bound>)
```

`<bound>` is, in order of preference: the thread's recorded `last_seen_ts`; else **the ts
of my own most recent message in that thread** (that is genuinely "since I last looked",
and avoids replaying my own words back at me on a thread's first appearance); else
`since_ts`.

Skip threads with no new replies. For the rest, write a short summary of **what changed**
and **what is being asked of me** — not a message-by-message transcript. Then record it:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" thread-seen --channel C... --thread-ts ... \
  --last-seen <newest reply ts> --title "..."
```

## 3b. Drop anything already recorded

The window overlaps by 30 minutes on purpose, so a run will re-collect items the previous
run already wrote. Before rendering:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/inbox_parse.py" --existing-ids
```

Compute each collected item's id (`m-`/`d-`/`t-` + channel + ts, as below) and **discard
any id already in that list**. Threads are the exception: a thread id recurs legitimately
when there are *new* replies, so for `t-` ids, keep it only if the delta fetch actually
returned new messages, and render it as a fresh section.

If everything was already recorded, insert nothing, do not advance the checkpoint by
writing an empty section, and just say "nothing new since <since_human>".

## 4. Rendering

Mentions and DMs are reproduced **verbatim** in a blockquote — never paraphrased, never
tidied. Resolve `<@U123|handle>` to `@handle` for readability, and leave everything else
exactly as written. Search results already carry channel name, author, ts and a permalink;
use them rather than constructing anything.

Write the new section to a temp file in the scratchpad, then insert it. Format per item:

```markdown
### mention · #general · Courtney · 12:48
<!-- item id=m-<channel>-<ts> kind=mention channel=<channel> ts=<ts> -->

> verbatim text here

[open in Slack](<permalink>)

<!-- reply id=m-<channel>-<ts> status=draft -->
<!-- /reply -->
```

- `kind=mention` → id prefix `m-`; `kind=dm` → `d-`; `kind=thread` → `t-` and add
  `thread_ts=<parent ts>` to the item anchor.
- Group items under `## <today's date>` with mentions first, then DMs, then threads.
- If a section is empty, say so in one line rather than omitting it.

## 5. Commit

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/inbox_write.py" insert --content-file <tmp file>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" commit
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" thread-prune
```

Commit **only after** the insert succeeds — a failed write must not advance the
checkpoint, or that window's messages are lost silently.

Finish with a one-line count (`3 mentions, 1 DM, 2 threads`) followed by the inbox path
that `inbox_write.py` printed, so I know which file to open. Nothing else. Do not paste
the review into the terminal; the file is the deliverable.
