---
description: Brief me for the daily Lead DS sync — what the Lead DS should review, open questions for both of us, recent developments, what to demo
argument-hint: "[period, e.g. 'since Monday' — default: since the last briefing]"
allowed-tools: Read, Write, Edit, Bash(git log:*), Bash(git status:*), Bash(git diff:*), Bash(git show:*)
---

Prepare a briefing for the daily Lead DS sync. Build it from the repo's markdown, never from chat
memory, so it works in a fresh chat.

1. Read `worknotes/sync.md` and the top of `worknotes/log.md` (create them from the templates in
   `worknotes/README.md` if missing). Then read `docs/UPDATES.md` and the Open decisions table in
   `docs/roadmap.md`.
2. Catch up. If `git log` shows commits that the log doesn't cover (a turn that forgot to log), add
   entries for them from the commit messages and diffs. Mention uncommitted work (`git status`).
3. Reply with, for the period "$ARGUMENTS" (default: since the last briefing):
   - **What happened:** 3–7 guiding bullets, newest first, each with why it matters.
   - **Demo:** the concrete code, notebook or doc to show, with the command to run and `path:line`.
     If nothing runnable exists yet, say which doc section to walk through.
   - **Discuss:** the open questions for this sync, most blocking first (OD-numbers, one line of
     context each, plus our current leaning).
   - **Risks / needs a decision:** anything blocked, unverified or drifting from the goals.
4. Refresh `sync.md` so it reads well for the Lead DS: tick or remove reviewed items, update the
   open-questions table and "Demo next", and set `last briefed`. Don't commit anything; the user
   commits and pushes.

Keep it skimmable: the user reads it right before a one-hour meeting. Roles only, no names; no bank
identifiers.
