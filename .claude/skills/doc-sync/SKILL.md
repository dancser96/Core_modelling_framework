---
name: doc-sync
description: Bring the repo documentation in line with the code and decisions at the end of a task, applying the update rules in CLAUDE.md §8 (owner docs, update triggers, creation rules, cross-links, local sync notes). Use this at the end of every task that changed code, config, dependencies, decisions or open questions, when the user says "update the docs", "sync docs", "wrap up", or before committing.
---

# Doc sync

The docs are how work continues across machines and sessions; chat history is lost. Stale docs are
worse than none. Docs describe the **current state**. History goes to the `docs/UPDATES.md` log and
to `docs/decisions.md`. The rules live in `CLAUDE.md` §8 (doc map, update triggers, when to create
a doc); this skill applies them.

## Steps

1. **List what changed:** `git status`, `git diff --stat`, plus the conversation's decisions,
   answered questions and new open questions.
2. **Apply the matching triggers** from `CLAUDE.md` §8. The ones most often missed:
   - a decision → a new D-row in `docs/decisions.md`, with superseded rows marked;
   - an open question opened, answered or parked → its OD row in `docs/roadmap.md` (an answered OD
     row becomes a D-row and is deleted);
   - a status change → `docs/UPDATES.md` (log line only if major) and the milestone/backlog in
     `docs/roadmap.md`;
   - a new or changed term → `docs/glossary.md`;
   - an artifact format or config change → the owning component doc + the `CLAUDE.md` §2 procedure.
3. **One owner per fact.** If the same fact now appears in two docs, keep it in its owner (§8 doc
   map) and replace the copy with a link.
4. **Cross-links.** Every component doc you touched has a correct **Related** line. Every new doc is
   registered in its index and linked both ways. After a rename or delete, `grep -rn "<old name>"`
   over `*.md` and fix every hit. Relative links must resolve.
5. **Style.** Edit text in place (integrate; don't append "update" sections). Verdict first,
   concise. Mark unverified claims as unverified. Roles, not names; no bank identifiers.
6. **Worknotes (shared with the Lead DS).** Refresh `worknotes/sync.md` following the rules in
   `worknotes/README.md` → "Writing `sync.md` for the LDS": new decisions by reference at the top,
   review list most important first then newest, "since the last sync" only for what changes the
   LDS's picture (one bullet per topic, no tooling or setup noise), and a terse "last 7 days" recap.
   Add to `worknotes/log.md`, merging into the existing entry when the same topic was updated the
   same or a neighbouring day (each update keeps its date). This happens every time, not only for big changes.
7. **Docs guide.** If a doc was added, renamed or deleted, update `docs/README.md` (reading order,
   stage → component map).
8. **Report** the doc files touched, one line each on what changed.

## Don't

- Don't write narrative history into component docs.
- Don't document code that doesn't exist yet as if it did (use "planned" / "designing").
- Don't create a new doc where an existing owner doc can be extended (`CLAUDE.md` §8 creation rules).
- Don't add bank names, paths, table names or people's names, including in `worknotes/`.
