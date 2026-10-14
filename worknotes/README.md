# worknotes — shared working notes (committed)

Working notes for **the framework's builder and the Lead DS**. They are committed, so they sync
between machines and the Lead DS can read them before the daily ~1h sync. Claude maintains them. They
are **never loaded at session start**; they are read only when asked (`CLAUDE.md` §0, §8).

| File | Purpose | Written | Read |
|---|---|---|---|
| `sync.md` | The sync page: new decisions, what the LDS should review, questions, what changed since the last sync | Refreshed at the end of every turn that changed files, settled something or produced a finding | Before each sync; `/brief` |
| `log.md` | The verbose trail, newest first: what changed, why, files, decisions | Appended at the same moments as `sync.md` | When the detail behind a sync item is needed |
| `chief_ds_meeting/` | Material for the Chief DS design meeting (2026-10-15): `overview.md` (15-minute direction pre-read) and `questions.md` (questions per topic) | Drafted with the builder before the meeting | In the meeting; delete once the outcomes are in `docs/decisions.md` and `docs/roadmap.md` |
| `handovers/<topic>.md` | A chat handover, one file per topic, so several topics can run in parallel | `/handover <topic>` (overwrites that topic's file) | Only via `/resume <topic>` |

**Rules**
- These files are visible to the Lead DS. No bank data, no internal identifiers, no people's names
  (roles only).
- They are not a second source of truth. Decisions go to `docs/decisions.md`, open questions to
  `docs/roadmap.md` (OD-nn), and status to `docs/UPDATES.md`. The notes link to them by number.
- Keep `sync.md` short enough to read in five minutes. Detail goes to `log.md`.

**Writing `sync.md` for the LDS.** The SDS works on the framework about 6 hours a day; the LDS spends
30–60 minutes, and only reads (code and markdown) and reviews, never writes or runs anything.
- **New decisions first, by reference only:** one line at the top, e.g. "D-056–D-061". The LDS reads
  them in `docs/decisions.md`; the sync page never restates them.
- **Review list: most important first, then newest.** An item stays until the SDS says the LDS has
  finished it (that news usually arrives a day later).
- **Since the last sync: only what changes the LDS's picture** (design, scope, findings, something
  ready to review, a blocker). One bullet per topic, merging same-day and same-topic updates. No
  tooling, package versions, machine setup or "notes recorded" items. Bullets the last sync
  covered are removed; their detail stays in `log.md`.
- **Last 7 days: a terse recap kept for circling back.** One line per topic (date or date range,
  what, where to look), main changes only, same noise rules. Lines older than seven days are
  removed.

**Writing `log.md`.** Verbose and log-like, newest first. Updates on the same topic from the same
or neighbouring days share one entry: the title carries the date range, each update keeps its date
as a sub-bullet, and the entry sits where its latest update falls.
- Commit and push the notes with the work they describe.

## `sync.md` template

~~~markdown
# Sync page
_For the SDS and the LDS · last updated: YYYY-MM-DD · last sync: YYYY-MM-DD_

**New decisions since the last sync:** D-nnn–D-nnn (`docs/decisions.md`)

## For the LDS: to review (most important first, then newest)
- [ ] <what to review> — <path> — feedback wanted: <the specific question>

## Questions for the LDS
- <question> (OD-nn) — <one line of context; our leaning>

## Open questions for both of us
| Question | Context | Current leaning | Needs |
|---|---|---|---|
| <question> (OD-nn) | <one line> | <leaning> | <who decides / forum> |

## Since the last sync
- **<topic>**: <what changed and why it matters to the LDS> — look at: <path>

## Demo next
- <what to show> — `<command or notebook cell>` · `<path:line>`

## Last 7 days
- MM-DD(–MM-DD) — **<topic>**: <one line> — <D-nnn / OD-nn / path>
~~~

## `log.md` entry template

~~~markdown
### YYYY-MM-DD(→ YYYY-MM-DD) — <topic>
- YYYY-MM-DD, <update>: …
- YYYY-MM-DD, <later update on the same topic>: …
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
