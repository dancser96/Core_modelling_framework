---
description: Resume one topic in a new chat from worknotes/handovers/<topic>.md
argument-hint: "<topic>"
allowed-tools: Read, Bash(ls:*), Bash(git status:*), Bash(git log:*), Bash(git diff:*)
---

Resume work on the topic "$ARGUMENTS".

1. If no topic was given, list `worknotes/handovers/` and ask which one.
2. Read `worknotes/handovers/$ARGUMENTS.md`, then the files under its "Read first" section, then
   `docs/UPDATES.md`.
3. Check what has changed since the handover was written (`git log` since its commit, `git status`).
   Say so if the handover is stale or contradicts the current docs; the docs win.
4. Reply with a five-line summary (goal, state, next step, open questions, anything stale). Then wait
   for instructions. Resuming is not approval to continue implementing.
