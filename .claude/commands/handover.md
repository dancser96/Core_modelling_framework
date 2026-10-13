---
description: Write a chat handover for one topic to worknotes/handovers/<topic>.md so a new chat can resume it
argument-hint: "<topic, short kebab-case name>"
allowed-tools: Read, Write, Edit, Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(git branch:*)
---

Write a handover for the topic "$ARGUMENTS" to `worknotes/handovers/$ARGUMENTS.md`, overwriting
that topic's file. If no topic was given, ask for one (a short kebab-case name). Other topics' files
stay untouched; several handovers can exist in parallel.

The reader is you, in a fresh chat with no memory of this one. Use the template in
`worknotes/README.md`. Include only what the repo docs don't already say, and link to them instead of
copying:
- **Goal:** what we are trying to achieve on this topic, and the user's intent in their own words.
- **State:** done / in progress / not started; uncommitted files (`git status`).
- **Decisions in this chat** not yet in `docs/decisions.md` (or their D-numbers if they are).
- **Open questions,** with the user's latest leaning.
- **Next steps:** the next 1–3 concrete actions, with files and functions.
- **Gotchas:** dead ends, things tried that failed, constraints that are easy to forget.
- **Read first:** the docs and files to load on resume, in order.

Keep it under ~150 lines. It is committed and visible to the Lead DS: no bank data, internal
identifiers or people's names. Then add a one-line entry to `worknotes/log.md`, and tell the user the exact resume command:
`/resume $ARGUMENTS`.
