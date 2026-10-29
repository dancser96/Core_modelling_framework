# worknotes — shared working notes (committed)

Working notes for **the framework's builder and the Lead DS**. They are committed, so they sync
between machines and the Lead DS can read them before the daily ~1h sync. Claude maintains them. They
are **never loaded at session start**; they are read only when asked (`CLAUDE.md` §0, §8).

| File | Purpose | Written | Read |
|---|---|---|---|
| `sync.md` | The sync page: what happened in short, what the LDS should review and decide, questions, what changed in the last 2 and 7 working days | Refreshed only by `/brief` or when the SDS asks (D-072 (h)) | Before each sync; `/brief` |
| `log.md` | The verbose trail, newest first: what changed, why, files, decisions | Appended at the end of every turn that changed files, settled something or produced a finding | When the detail behind a sync item is needed |
| `handovers/<topic>.md` | A chat handover, one file per topic, so several topics can run in parallel | `/handover <topic>` (overwrites that topic's file) | Only via `/resume <topic>` |
| `<stage>/` (now `m2_1_foundation/`) | The folder of the stage being built: its design questions with defaults, the agreed build plan, the review guide; files leave once settled, so a stage under review holds its review guide alone (2026-10-29). Written for the SDS, the active developer; an LDS review joins it only when the SDS asks for one (D-072 (i)). One folder at a time; deleted when the stage is done (the SDS, 2026-10-23) | At the start of each stage, updated through it | The SDS answers the questions, approves the plan and reviews with the guide |
| `timeline_proposal.md` | What is left of the planning-session set of 2026-10-20: the Phase 2 plan, the working assumption under review (D-022, OD-01), until its dates and depth move to `docs/roadmap.md` | Once, by request; deleted when the SDS says | When the plan is shared with the CDS |

**Rules**
- These files are visible to the Lead DS. No bank data, no internal identifiers, no people's names
  (roles only).
- They are not a second source of truth. Decisions go to `docs/decisions.md`, open questions to
  `docs/roadmap.md` (OD-nn), and status to `docs/UPDATES.md`. The notes link to them by number.
- Keep `sync.md` short enough to read in five minutes. Detail goes to `log.md`.

**Writing `sync.md` for the LDS.** The SDS works on the framework about 6 hours a day; the LDS spends
30–60 minutes. The LDS reads the design and the important parts of the code, not all of it, tries
the functionality and the notebooks, and reviews; they never write code (D-072 (i)).
- **Windows count working days (Monday to Friday).** The 2-day window opens at the start of the
  second-to-last working day up to today and runs to now, so weekend work always falls inside it
  (on a Monday: Friday to Monday). The 7-day window opens at the seventh-to-last working day.
  Each section heading carries its dates.
- **"In short" first: what actually happened, in plain words.** Three to eight lines on the 2-day
  window: what was done, settled or found, and what it means for the LDS. Context only: no D-, OD-
  or Q-numbers and no paths; the references sit in the bullets below.
- **Review list: most important first, then newest, without tags.** One bold line above the list
  points to the decisions the LDS must take: the short-term open decisions in `docs/roadmap.md`,
  by OD-number. A decision never appears as a review item or a tag; the items are things to read,
  each short (about three lines): what, where, the feedback wanted. A code item names the few
  functions that carry the ML logic (`path` → `function`), never a whole module or "the code in
  full". An item stays until the SDS says the LDS has finished it (that news usually arrives a day
  later), or the SDS drains the list.
- **"To try": what the LDS can run themselves.** A notebook or a command, and what to look for.
- **The two recent-changes sections focus on what matters.** Only important changes and updates
  that change the LDS's picture (design, scope, findings, something ready to review, a blocker),
  never an info dump: pick, don't list everything. No tooling, package versions, machine setup or
  "notes recorded" items; the detail stays in `log.md`.
- **Last 2 working days: a soft ceiling of 40 lines and a hard ceiling of 50** (lines of the file,
  heading included; count them before finishing). One bullet per topic, merging same-topic updates
  across the window. A bullet that leaves the window moves down into the 7-day recap as one line.
- **Last 7 working days: a terse recap kept for circling back**, for working days 3–7, at most one
  page. One line per topic (date or date range, what, where to look). Lines that leave the window
  are removed.

**Writing `log.md`.** Verbose and log-like, newest first. Updates on the same topic from the same
or neighbouring days share one entry: the title carries the date range, each update keeps its date
as a sub-bullet, and the entry sits where its latest update falls.
- The notes go into the same commit as the work they describe (commits only when the SDS asks).

## `sync.md` template

~~~markdown
# Sync page
_For the SDS and the LDS · last updated: YYYY-MM-DD · last sync: YYYY-MM-DD_

**In short (MM-DD to MM-DD):** <three to eight lines in plain words: what happened, what it means for the LDS; no references>

## For the LDS: to review (most important first, then newest)
**Decisions needed from you: the short-term open decisions** in `docs/roadmap.md` → Open decisions (OD-nn, OD-nn, …)
- [ ] **<what to review>** — <path> — feedback wanted: <the specific question>

## Questions for the LDS
- <question> (OD-nn) — <one line of context; our leaning>

## Open questions for both of us
| Question | Context | Current leaning | Needs |
|---|---|---|---|
| <question> (OD-nn) | <one line> | <leaning> | <who decides / forum> |

## Last 2 working days (MM-DD to MM-DD)
- **<topic> (MM-DD(→ MM-DD))**: <what changed and why it matters to the LDS> — look at: <path / D-nnn>

## To try
- <what to try> — `<notebook or command>` · what to look for

## Last 7 working days (MM-DD to MM-DD)
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
