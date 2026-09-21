# slack-daily-review

A daily Slack catch-up that writes to a file you can reply in.

`/slack-daily-review:slack-review` collects what wants your attention since the last run
and prepends it to your `INBOX.md`: **mentions and DMs verbatim**, **threads summarized**
since you last looked. You type replies inline. `/slack-daily-review:slack-post` sends
them.

## Install

Requires **Python 3** on your `PATH`, and the Slack MCP plugin, which ships Slack's own
OAuth client:

```
/plugin install slack@claude-plugins-official
```

Authenticate once in the browser. No custom Slack app and no admin approval are needed —
the plugin carries a registered first-party client id.

Then install this one:

```
/plugin marketplace add jcounts/slack-daily-review
/plugin install slack-daily-review@slack-daily-review
```

### Claude Desktop

The desktop app's plugin browser (**+** → **Plugins** → **Add plugin**) can only install
from marketplaces that are *already configured* — it has no UI for adding a third-party
marketplace. Run the `marketplace add` line above in the Claude Code CLI once; the plugin
then appears in the desktop browser. Plugins are unavailable in WSL sessions, and
desktop-installed plugins don't carry into cloud sessions.

## Where your data lives

Your inbox and checkpoint are kept **outside** the plugin directory, because a plugin
update replaces that directory wholesale and would take the checkpoint with it:

```
~/.slack-daily-review/INBOX.md            # the file you type replies into
~/.slack-daily-review/state/checkpoint.json
~/.slack-daily-review/state/posted.log    # local audit trail of what was sent
```

Set `SLACK_DAILY_REVIEW_HOME` to put them somewhere else — a project directory, or a
synced folder. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/paths.py"` prints the resolved
paths.

## Use

```
/slack-daily-review:slack-review              # collect into INBOX.md
# ...open INBOX.md, type between the `reply` markers...
/slack-daily-review:slack-post --dry-run      # see exactly what would go where
/slack-daily-review:slack-post                # send, after confirming
/slack-daily-review:slack-post --draft        # create Slack drafts instead of sending
```

An empty reply block is skipped. Sent replies flip to `status=sent`, so running
`/slack-daily-review:slack-post` twice never double-posts.

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
- That trick relies on undocumented tokenization, so `/slack-daily-review:slack-review` sanity-checks it and
  complains loudly rather than reporting a falsely quiet day.
- **Messages posted through this MCP are tagged "Sent using Claude" in Slack.** Visible to
  recipients, unavoidable.
- There is no read-state API. "Notifications" is approximated by a time window plus a local
  checkpoint (with 30 min overlap and id-based dedup), never by Slack's actual unreads.

## Tests

```bash
./run-tests.sh      # 39 offline unit tests; never touch Slack
/slack-daily-review:slack-selftest   # live canary against Slack's actual search behaviour
```

The offline suite covers reply routing (mention → in-thread, DM → unthreaded, thread →
parent ts), the refusals that matter (`sent` skipped, empty skipped, orphan reported
rather than guessed at), body fidelity, and the window/TTL logic.

`/slack-daily-review:slack-selftest` is the one that guards the caveats above. The quoted-mention trick and
`to:me`'s DM-only behaviour live in Slack's remote service, not in this repo, so they
cannot be unit tested — but their failure mode is an empty result set, which is
indistinguishable from a quiet day. The canary runs the real queries against known
fixture messages and fails loudly, naming the fallback to switch to. Its assertion logic
*is* unit tested, against synthetic output simulating each way the behaviour could break.

## Developing on it

Load the working copy directly instead of installing:

```bash
claude --plugin-dir /path/to/slack-daily-review
```

`/reload-plugins` picks up edits without restarting. Skills live in `skills/<name>/SKILL.md`;
bundled scripts are referenced as `"${CLAUDE_PLUGIN_ROOT}/scripts/..."` so they resolve
from the install directory rather than your current one.

Full empirical notes: `docs/spike-findings.md`. Design: `PLAN.md`.
