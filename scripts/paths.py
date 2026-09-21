#!/usr/bin/env python3
"""Where slack-daily-review keeps *your* data, as opposed to its own code.

This split only matters once the tool is installed as a plugin. A plugin's
directory is replaced wholesale when the plugin updates, so anything stored
next to these scripts -- the checkpoint, the posted log, INBOX.md -- would be
silently discarded on the next version bump. None of it is recoverable from
Slack: the checkpoint is the only record of what has already been reviewed,
and posted.log is a local audit trail that exists nowhere else.

So user data lives in a stable directory outside the plugin:

    $SLACK_DAILY_REVIEW_HOME, if set
    ~/.slack-daily-review, otherwise

Set the env var to keep the inbox inside a project or a synced folder.
"""
from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "SLACK_DAILY_REVIEW_HOME"
DEFAULT_HOME = Path.home() / ".slack-daily-review"


def data_dir() -> Path:
    override = os.environ.get(ENV_VAR)
    return Path(override).expanduser().resolve() if override else DEFAULT_HOME


def inbox_path() -> Path:
    return data_dir() / "INBOX.md"


def state_path() -> Path:
    return data_dir() / "state" / "checkpoint.json"


def posted_log_path() -> Path:
    return data_dir() / "state" / "posted.log"


if __name__ == "__main__":
    import json
    print(json.dumps({
        "data_dir": str(data_dir()),
        "inbox": str(inbox_path()),
        "state": str(state_path()),
        "posted_log": str(posted_log_path()),
        "source": ENV_VAR if os.environ.get(ENV_VAR) else "default",
    }, indent=2))
