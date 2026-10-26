# Second brain, dashboard and AI workers

## What it is
1. A dashboard for Jo's life: calendars, inboxes, tasks and tools on one page, refreshed every morning.
2. A second brain: this repo, readable by Codex and Claude, growing over time.
3. An AI executive assistant: plans the day before Jo wakes, sweeps at midday, and checks at night what got done against his goals.
[jo, 2026-10-17]

## How it's built
See docs/BUILD.md. Workers run on GitHub Actions with openai/codex-action. Messages to other people wait for Jo's approval as outbox issues.

## History
A Claude scheduled task, "Parcel Daily Briefing", has written Jo's morning briefing since July 2026. workers/morning-briefing.md is ported from its spec. [verified 2026-10-17]
