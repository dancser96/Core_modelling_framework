# worknotes — shared working notes (committed)

Working notes for **the framework's builder and the Lead DS**. They are committed, so they sync
between machines and the Lead DS can read them before the daily ~1h sync. Claude maintains them. They
are **never loaded at session start**; they are read only when asked (`CLAUDE.md` §0, §8).

| File | Purpose | Written | Read |
|---|---|---|---|
| `sync.md` | The sync page: new decisions, what the LDS should review, questions, what changed in the last 2 and 7 days | Refreshed at the end of every turn that changed files, settled something or produced a finding | Before each sync; `/brief` |
| `log.md` | The verbose trail, newest first: what changed, why, files, decisions | Appended at the same moments as `sync.md` | When the detail behind a sync item is needed |
| `handovers/<topic>.md` | A chat handover, one file per topic, so several topics can run in parallel | `/handover <topic>` (overwrites that topic's file) | Only via `/resume <topic>` |
| `decisions_LDS_review.md` | The twenty decisions the LDS should read first, in reading order, with why each matters and what feedback is wanted; rows leave once reviewed, new high-impact decisions join | By the SDS's request (2026-10-22); maintained by Claude as decisions land and reviews finish | The LDS, between syncs |
| `inconsistency_questions.md` | Numbered questions from the inconsistency sweep of 2026-10-22 (decisions vs open decisions vs descriptions), each with a proposed default; answered questions leave the file and become D-rows, OD rows or doc fixes | Once, by request; updated as answers arrive | The SDS answers; the LDS may weigh in |
| `holistic_review_questions.md`, `timeline_proposal.md` | What is left of the planning-session set of 2026-10-20: the closed questions file, and the Phase 2 plan, the working assumption under review (D-022, OD-01). The review itself was deleted on 2026-10-22, its outcomes being in `docs/` | Once, by request; deleted when the SDS says | When the plan is shared with the CDS |

**Rules**
- These files are visible to the Lead DS. No bank data, no internal identifiers, no people's names
  (roles only).
- They are not a second source of truth. Decisions go to `docs/decisions.md`, open questions to
  `docs/roadmap.md` (OD-nn), and status to `docs/UPDATES.md`. The notes link to them by number.
- Keep `sync.md` short enough to read in five minutes. Detail goes to `log.md`.

**Writing `sync.md` for the LDS.** The SDS works on the framework about 6 hours a day; the LDS spends
30–60 minutes, and only reads (code and markdown) and reviews, never writes or runs anything.
- **New decisions first, by reference only:** one line at the top, e.g. "D-129–D-131". The LDS reads
  them in `docs/decisions.md`; the sync page never restates them.
- **Review list: most important first, then newest.** Every item is tagged **needs decision** or
  **for information**, and at most five "needs decision" items are open at once (D-072). The LDS
  reviews design docs and the ML-critical code (dataset, Target Factory, training, calibration,
  evaluation) in full and samples the rest. An item stays until the SDS says the LDS has
  finished it (that news usually arrives a day later), or the SDS drains the list.
- **Last 2 days and last 7 days are each at most one page, and focus on what matters.** Only
  important changes and updates that change the LDS's picture (design, scope, findings, something
  ready to review, a blocker), never an info dump: pick, don't list everything. No tooling,
  package versions, machine setup or "notes recorded" items; the detail stays in `log.md`.
- **Last 2 days:** one bullet per topic, merging same-day and same-topic updates. A bullet older
  than two days moves down into the 7-day recap as one line.
- **Last 7 days: a terse recap kept for circling back**, for days 3–7. One line per topic (date or
  date range, what, where to look). Lines older than seven days are removed.

**Writing `log.md`.** Verbose and log-like, newest first. Updates on the same topic from the same
or neighbouring days share one entry: the title carries the date range, each update keeps its date
as a sub-bullet, and the entry sits where its latest update falls.
- The notes go into the same commit as the work they describe (commits only when the SDS asks).

## `sync.md` template

~~~markdown
# Sync page
_For the SDS and the LDS · last updated: YYYY-MM-DD · last sync: YYYY-MM-DD_

**New or extended decisions in the last 2 days:** D-nnn–D-nnn (`docs/decisions.md`)

## For the LDS: to review (most important first, then newest)
- [ ] **<what to review>** (needs decision | for information) — <path> — feedback wanted: <the specific question>

## Questions for the LDS
- <question> (OD-nn) — <one line of context; our leaning>

## Open questions for both of us
| Question | Context | Current leaning | Needs |
|---|---|---|---|
| <question> (OD-nn) | <one line> | <leaning> | <who decides / forum> |

## Last 2 days
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
