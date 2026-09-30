---
name: doc-sync
description: Bring the repo documentation in line with the code at the end of a task, applying the update rules in CLAUDE.md §8. Use this at the end of every task that changed code, config, dependencies or decisions, when the user says "update the docs", "sync docs", "wrap up", or before committing.
---

# Doc sync

The docs are how work continues across machines and sessions; chat history is lost. Stale docs are
worse than none. Docs describe the **current state**. History goes to `docs/UPDATES.md` (log) and
`docs/decisions.md`.

## Steps

1. List what changed: `git diff --stat` plus the conversation's decisions.
2. For each change, apply the matching rule(s):

| Change | Update |
|---|---|
| Component behaviour or interface | `docs/components/<c>.md` — Status, Interface, requirements met |
| Config field added/changed/removed | `docs/components/config.md`, example in `conf/base/`; breaking → CLAUDE.md §2 procedure |
| Decision made | New row in `docs/decisions.md`; `docs/architecture.md` if structure changed |
| Work item progressed | `docs/UPDATES.md` status table; a dated log line only if major |
| New bug class / trap | `docs/context/lessons.md` → Known traps (next T-number) |
| Environment fact | `docs/context/environment.md` + `requirements.txt` |
| Public function added/changed | `docs/architecture.md` → Public API table |
| New skill/agent | `docs/guides/skills_and_agents.md` inventory |
| Scope/goals/priorities | `docs/context/project.md` |

3. Edit existing text in place (integrate; don't append new sections). Keep it verdict-first and
   concise. Mark unverified claims as unverified.
4. Report the list of doc files touched, with one line each on what changed.

## Don't

- Don't write narrative history into component docs.
- Don't document code that doesn't exist yet as if it did (use "planned" / "designing").
- Don't add bank names, paths, table names or people's names.
