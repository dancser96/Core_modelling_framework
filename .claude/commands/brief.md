---
description: Brief me for the daily Lead DS sync — what the Lead DS should review and try, open questions for both of us, recent developments
argument-hint: "[period, e.g. 'since Monday' — default: since the last briefing]"
allowed-tools: Read, Write, Edit, Bash(git log:*), Bash(git status:*), Bash(git diff:*), Bash(git show:*)
---

Prepare a briefing for the daily Lead DS sync. Build it from the repo's markdown, never from chat
memory, so it works in a fresh chat.

1. Read `worknotes/sync.md` and the top of `worknotes/log.md` (create them from the templates in
   `worknotes/README.md` if missing). Then read `docs/UPDATES.md` and the Open decisions tables in
   `docs/roadmap.md` (short-term first).
2. Catch up. If `git log` shows commits that the log doesn't cover (a turn that forgot to log), add
   entries for them from the commit messages and diffs. Mention uncommitted work (`git status`).
   Then delete the log entries older than 7 working days (git keeps them, D-072 (h)).
3. Reply with, for the period "$ARGUMENTS" (default: since the last briefing):
   - **What happened:** 3–7 guiding bullets, newest first, each with why it matters: the essence
     of the updates and the EDS's key decisions, never how many rounds or reviews it took.
   - **To try:** the notebook or command the LDS can run themselves, and what to look for. If
     nothing runnable exists yet, say which doc section to walk through.
   - **Discuss:** the open questions for this sync, most blocking first (OD-numbers, one line of
     context each, plus our current leaning).
   - **Risks / needs a decision:** anything blocked, unverified or drifting from the goals.
4. Refresh `sync.md` following the rules in `worknotes/README.md` → "Writing `sync.md` for the LDS":
   "In short" at the top in plain words without references, focused on the key decisions made,
   one line pointing to the short-term open decisions above an untagged review list by importance
   then recency that gives the EDS's recent key decisions as much room as the open ones (tick or
   remove only items the user says the LDS finished), no timelines anywhere on the page, "last 2 working days" (soft ceiling 40 lines, hard 50) and
   "last 7 working days" (at most one page) pruned to the important changes, the open-questions
   table and "To try" updated, and `last sync` set. Don't commit anything; the user
   commits and pushes.

Keep it skimmable: the user reads it right before a one-hour meeting. Roles only, no names; no bank
identifiers.
