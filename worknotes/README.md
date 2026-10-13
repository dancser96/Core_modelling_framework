# worknotes — shared working notes (committed)

Working notes for **the framework's builder and the Lead DS**. They are committed, so they sync
between machines and the Lead DS can read them before the daily ~1h sync. Claude maintains them. They
are **never loaded at session start**; they are read only when asked (`CLAUDE.md` §0, §8).

| File | Purpose | Written | Read |
|---|---|---|---|
| `sync.md` | The sync page: what the Lead DS should review, open questions for both of us, recent developments | Refreshed at the end of every turn that changed files, settled something or produced a finding | Before each sync; `/brief` |
| `log.md` | The verbose trail, newest first: what changed, why, files, decisions | Appended at the same moments as `sync.md` | When the detail behind a sync item is needed |
| `handovers/<topic>.md` | A chat handover, one file per topic, so several topics can run in parallel | `/handover <topic>` (overwrites that topic's file) | Only via `/resume <topic>` |

**Rules**
- These files are visible to the Lead DS. No bank data, no internal identifiers, no people's names
  (roles only).
- They are not a second source of truth. Decisions go to `docs/decisions.md`, open questions to
  `docs/roadmap.md` (OD-nn), and status to `docs/UPDATES.md`. The notes link to them by number.
- Keep `sync.md` short enough to read in five minutes. Detail goes to `log.md`.
- Commit and push the notes with the work they describe.

## `sync.md` template

~~~markdown
# Sync page
_For the builder and the Lead DS · last updated: YYYY-MM-DD · last briefed: YYYY-MM-DD_

## For the Lead DS: to review
- [ ] <what to review> — <doc section link> — feedback wanted: <the specific question or decision>

## Open questions for both of us
| Question | Context | Current leaning | Needs |
|---|---|---|---|
| <question> (OD-nn) | <one line> | <leaning> | <who decides / forum> |

## Recent developments (newest first)
- YYYY-MM-DD — <what changed> · why: <reason> · look at: <path> · status: done / in progress

## Demo next
- <what to show> — `<command or notebook cell>` · `<path:line>`
~~~

## `log.md` entry template

~~~markdown
### YYYY-MM-DD — <title>
- What: …
- Why: …
- Files: …
- Decisions / open decisions: D-nnn, OD-nn
- Still open: …
~~~

## Handover template (`handovers/<topic>.md`)

~~~markdown
# Handover: <topic>
_Written: YYYY-MM-DD HH:MM · branch: <branch> · last commit: <sha>_

## Goal
## State (done / in progress / not started; uncommitted files)
## Decisions in that chat (not yet in docs/decisions.md)
## Open questions (with the user's latest leaning)
## Next steps (1–3 concrete actions, with files and functions)
## Gotchas (dead ends, constraints easy to forget)
## Read first (docs and files, in order)
~~~
