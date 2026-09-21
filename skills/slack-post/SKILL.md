---
description: Post the replies drafted in INBOX.md back to Slack, after confirmation
disable-model-invocation: true
---

Send the replies I typed into the inbox file. Arguments: $ARGUMENTS
(`--dry-run` = show what would be sent and stop; `--draft` = create Slack drafts
instead of sending.)

## 1. Parse

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/inbox_parse.py"
```

The script resolves the inbox path itself (default `~/.slack-daily-review/INBOX.md`, or
`$SLACK_DAILY_REVIEW_HOME`). Do not pass `--inbox` unless I ask for a specific file.

Exit code 2 means malformed blocks. **Report the `problems` list and stop** — do not send
a partial batch when the file is inconsistent. An orphan reply (no matching item anchor)
has no known destination and must never be guessed at.

If `count` is 0, say "no drafted replies" and stop.

## 2. Confirm — always

Print a numbered table of destination and exact text. Resolve channel ids to names
(`slack_search_channels`, or the `#name` already in the item heading) so I can actually
tell where each one is going:

```
1. #general · threaded reply under Courtney's 12:48 message
   "Sure, Friday works. Booking it now."
2. DM with Courtney
   "hey, replying here"
```

Then **ask me to confirm before sending anything.** Posting to Slack is outward-facing and
cannot be undone. Never send on an assumed yes, and never send just because the file
contained drafts. Stop here if `--dry-run`.

Also state once, before the first real send of a session: messages posted through this MCP
are visibly tagged **"Sent using Claude"** in Slack.

## 3. Send

For each pending reply, in the order listed:

```
slack_send_message(channel_id: <channel>, message: <text>, thread_ts: <thread_ts if not null>)
```

`thread_ts` comes from the parser and encodes the routing (mentions reply in-thread, DMs
post unthreaded). Do not override it. Send the text **exactly** as typed — do not
reformat, expand, correct, or add a sign-off.

With `--draft`, use `slack_send_message_draft` instead, then tell me to review the drafts
in Slack. Do not mark those as sent — they have not been.

## 4. Record — after each successful send

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/inbox_write.py" mark-sent --id <id> --ts <returned message_ts> --permalink <returned link>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" posted-log --id <id> --channel <channel> --permalink <returned link>
```

Mark each one immediately after its own send, not in a batch at the end — if the run dies
midway, everything already sent is recorded and will not be resent.

If a send fails, leave that block as `draft`, report the error, and continue with the rest.

Then register replied-to threads so follow-ups get picked up next review:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/slack_state.py" thread-seen --channel <channel> --thread-ts <thread_ts> --last-seen <returned ts>
```

## 5. Report

One line per reply: where it went and its permalink. Then stop.
