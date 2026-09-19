# Phase 0 spike findings — RESOLVED

Workspace `apptesting-9pl4296` · me = `U0C2Y3CB0BX` (jcounts) · partner = `U0C2Y8980GM` (CC)
Server `https://mcp.slack.com/mcp` via `slack@claude-plugins-official` v1.3.0
(Slack-published OAuth client `1601185624273.8899143856786`, public client + PKCE).
Date: 2026-09-19.

## The validated query set

These three queries are the whole collector. All verified against a two-account fixture set.

### 1. Mentions in channels

```
keywords: ["\"<@U0C2Y3CB0BX>\""]     # quoted exact phrase, raw mention markup
filters:  -from:me after:YYYY-MM-DD
```

Returns exactly the messages mentioning me, self-mentions excluded. Verified: matched
CC's `#general` mention, correctly dropped my own identical-shaped fixture.

**This was the hard-won result.** The mention markup is only findable as a *quoted exact
phrase* on the bare form `"<@Uxxx>"`. Note the indexed text is actually
`<@U0C2Y3CB0BX|jcounts>` — the bare form still matches, but an unquoted keyword does not.

### 2. DMs and group DMs

```
filters: to:me
after:   <unix ts>        # the numeric param, not the after: modifier
```

Returns DMs sent to me by others. Verified: matched CC's DM, excluded everything else.

### 3. Threads I'm involved in

```
filters: is:thread from:me        # discovery — threads I've posted in
```
then per thread:
```
slack_read_thread(channel_id, message_ts=<parent ts>, oldest=<last_seen_ts>)
```

Verified: discovery returned my thread parent + my reply; `oldest` returned only the one
new reply from CC, plus the parent as context. This is the "since last update" mechanism
and it works exactly as needed.

## Negative results (things that do NOT work)

1. **`to:me` does NOT find channel mentions.** It is DM-only. Proven with a clean
   discriminator: CC's `#general` mention and CC's DM were posted 15 seconds apart;
   `to:me` returned only the DM.
   **This contradicts the plugin's own `slack-search` skill**, which documents `to:me` as
   "messages sent directly to you" and omits `is:dm`; the tool schema omits `to:` and
   documents `is:dm`. Trust the schema, not the skill doc.
2. **Keyword search matches the AUTHOR field.** Keyword `jcounts` returned all 5
   self-authored fixtures including a control containing no mention. With `from:<@CC>` it
   returned nothing. So you cannot find mentions by searching your own handle — it
   collides with your own authorship.
3. **`@jcounts` as a keyword matches nothing** — the leading `@` breaks tokenization.
4. **Unquoted `<@U0C2Y3CB0BX>` does not reliably match; quoting is required.**
5. **Semantic search is disabled for this account** (stated in two tool schemas), so
   `natural_language_query` reranking cannot be relied on. Keywords + filters only.

## Other established facts

- **No custom Slack app, no admin approval** (in a workspace you own). One browser consent.
- **30 tools live**, more than the docs implied. `slack_list_user_channels` exists, so
  channel/DM enumeration is available as a fallback to search.
- **Indexing is ~immediate** — fixtures were searchable seconds after posting. The
  "search is not real-time" warning is mild at this scale, but keep a window overlap anyway.
- **Search hits are self-sufficient for the digest**: channel id + name, author id + name
  + email, `Message_ts`, ready-made permalink, `Reply count`; a reply's permalink carries
  `?thread_ts=`. No follow-up calls, no hand-built permalinks.
- **Messages posted via this MCP are visibly tagged `*Sent using* Claude`** in Slack.
  Unavoidable and user-visible — worth knowing before replies go to real colleagues.
- Display names are inconsistent between tools: the same user appeared as `CC` via
  `slack_read_channel` and `Courtney` via search. Prefer the user ID as the key.
- Mentions render as `<@Uxxx|handle>`; resolve to `@handle` when writing verbatim text.
- Limits: search `limit` max 20 + cursor; `slack_read_channel` max 100 with
  `oldest`/`latest`; `slack_read_thread` max 1000 with `oldest`/`latest`.
  `response_format: "concise"` + `include_context: false` cut response size substantially.

## Consequence for the design

The search-based collector is viable and cheap — three queries per run, not a per-channel
sweep. The `slack_list_user_channels` + per-channel-read fallback is **not needed** as the
primary path, though it remains the escape hatch if the quoted-mention trick ever regresses
(it depends on undocumented tokenization behavior, so the skill should assert a non-empty
result when mentions are expected and fall back loudly rather than silently reporting
"nothing today").
