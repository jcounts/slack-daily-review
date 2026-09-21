#!/usr/bin/env bash
# Offline unit tests. These never touch Slack.
# For the LIVE contract canary against Slack's actual search behaviour, run
# /slack-daily-review:slack-selftest in Claude Code instead.
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s tests "$@"
