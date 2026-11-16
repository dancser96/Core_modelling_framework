---
name: delegation
description: Split a task into parallel subagent work, route each piece to the model and effort that match the cost of a wrong answer, and brief every agent completely. Use at the start of every non-trivial task (anything with two or more independent pieces of research, review, code, tests or docs), when implementation of an approved CLAUDE.md §1 plan starts, when running the review subagents, and whenever a task needs more than a few tool calls of searching or reading. Skip it only for a single small edit.
when_to_use: Trigger phrases include "delegate", "in parallel", "subagents", "split this up", "fan out", "orchestrate", "use a cheaper model", "use sonnet / haiku for", "run the reviews", "build these at once". Also any plan with several minor steps, any review round, any research question, any audit.
---

# Delegation

Work runs in parallel by default (D-072, `CLAUDE.md` §1 workflow). The main thread's context is
the scarce resource: it holds the plan, the EDS's decisions and the integration. Everything that
doesn't need the whole picture goes to a subagent. Only mechanical, fully checked pieces go to a
cheaper model; judgement stays on a strong one. A subagent starts with no context, so the brief
is its whole job description.

## 1. Split

List the pieces before touching anything. A piece qualifies for delegation when it:
- has one clear deliverable: a function with its tests, a doc section, a finding list, an answer;
- can be checked: a test, `ruff`, a diff the main thread reads, a source to cite;
- owns its files, and no other parallel piece touches them. If two pieces need the same file,
  merge them or run them in sequence.

Stays on the main thread: the plan and its approval, anything that needs the whole picture,
integration, and the conversation with the EDS. Don't do the pieces yourself after planning
them; that is the usual failure.

## 2. Research is not design

Research gathers and checks evidence: what is true, which options exist, what others do and with
what results, each with a source. Design decides what this repo does: it weighs that evidence
against the goals, the decision log, the constraints and the EDS's view. Brainstorming, the plan
and every choice between options are design, and design never leaves the main thread.

- A research brief asks "what is true?" or "what are the options and their evidence?", never
  "what should we do?".
- A researcher may add a leaning, labelled as one. The main thread decides, with the EDS.
- Inside `brainstorming`, the research step can be delegated; the critique and the design can't.

## 3. Route

Route by the cost of a wrong answer and how cheaply it can be checked, not by how small the piece
looks. A cheaper model takes only mechanical work that a test, a command or the main thread
reading the whole diff checks in full. Anything that feeds a decision, anything the EDS or LDS
reads as the record, and anything touching §4 runs on a strong model.

- **The repo's worker agents pin their tools, model and effort** (D-072 (o)): `builder` (Opus,
  `high`), `researcher` (Sonnet, `high`), `doc-writer` (Opus, `high`). Pass `model` or `effort`
  on the `Agent` call only to deviate, as the tables say. They start at less than half the
  context of `general-purpose`, which is left for a piece none of them fits.
- **Strong** means Opus. On a Fable session, Fable keeps the main thread and the
  `ml-correctness-auditor`; any other subagent runs on Fable only when the routing plan says why
  (D-072 (l)). The review agents inherit the session model, so pass them `model: opus` and an
  `effort`: what an agent runs at without one isn't documented.
- Never set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` or `CLAUDE_CODE_EFFORT_LEVEL`: they override every
  agent, the auditors included.

**Research**

| Piece | Agent type | Model, effort to pass |
|---|---|---|
| Locate: where something lives in the repo or on a docs site | `Explore` | haiku, low |
| Fact check: one API or behaviour in the pinned version, quoting `file:line` of the installed package or the tagged source | `researcher` | none (sonnet, high) |
| Fact check that traces behaviour through several code paths or libraries | `researcher` | `model: opus` |
| Best practice and literature: options and their evidence (§1 step 0, `brainstorming`) | `researcher` | `model: opus`; `effort: xhigh` for a major step |

**Code and tests**

| Piece | Agent type | Model, effort to pass |
|---|---|---|
| Mechanical change: rename, move, apply an established pattern | `builder` | `model: sonnet`, `effort: medium` |
| A minor step from a complete brief, with the signatures given | `builder` | `model: sonnet` |
| Code in Target Factory, dataset and splits, features, training, calibration, evaluation or inference, or any §4 path | `builder` | none (opus, high); `effort: xhigh` where the routing plan says so |
| Tests for a specified function | `builder` | `model: sonnet` |
| Tests for a §4 invariant or a §2 migration path | `builder` | none (opus, high) |

**Docs.** They are how the EDS and the LDS see the work, so the cheaper model only propagates
text whose substance is already settled.

| Piece | Agent type | Model, effort to pass |
|---|---|---|
| Propagation: a renamed term, cross-references, index and inventory rows, text the main thread wrote | `doc-writer` | `model: sonnet`, `effort: medium` |
| Component doc content: a design section or a three-level rewrite, from substance given in the brief | `doc-writer` | none (opus, high) |
| `worknotes/sync.md` and `log.md`, `docs/decisions.md` rows, OD rows, `docs/UPDATES.md`, review guides, the report to the EDS | main thread | session |

**Reviews and design**

| Piece | Agent type | Model, effort |
|---|---|---|
| `code-reviewer`, `silent-failure-hunter`, `compat-guardian` | that agent | strong, high |
| `ml-correctness-auditor` | that agent | strong, xhigh |
| Design, the plan, choices between options, integration | main thread | session |

Escalate a piece to a strong model when it turns out to need judgement, or when a cheaper attempt
failed once. Never retry the same brief on the same model. A cheaper model's output isn't done
until the main thread has read it in full and a strong reviewer has seen it (step 6).

**Routing plan on a Fable session** (D-072 (l)). Before a major task, show the EDS, with the plan
and before spawning, one table: piece, agent type, model and effort, why. Nearly all of the
subagent work goes to Opus, Sonnet and Haiku per the tables above. The point is balance: without
the plan, almost every token goes to Fable.

## 4. Brief

Every brief has these parts, in this order. Short is fine; missing is not.

1. **Goal**: one sentence, plus why, so the agent can make the small calls itself.
2. **Read first**: the exact files and sections: the component doc and which of its three levels,
   the trap numbers in `docs/context/lessons.md`, the legacy reference if any. `CLAUDE.md` is
   already in every agent's context: name the § that matters and never ask for a re-read.
3. **Files you own**, and files you must not touch.
4. **Specifics**: the function names and signatures from the plan, and anything this piece must
   not do. The worker agents already carry the §1 rules, the test and no-Spark rules, the report
   format and the stop rule; spell those out only for `general-purpose`.
5. **Acceptance**: the commands to run and the expected result (`pytest tests/test_x.py`,
   `ruff check <files>`): only the tests of the files the agent owns, never the full suite
   (D-072 (m)). The agent runs them and reports the output, not a claim.
6. **Report and stop rule**: the worker agents' own (at most ~15 lines, no pasted files; stop and
   report when a constraint can't be met). Add only what this piece needs reported on top.

Two variants:
- **Research brief**: parts 3–5 become the question (what is true, or what the options are), the
  pinned version to check against, and where to look first. The report gives the evidence with
  sources, conflicts between sources, what is unverified, and at most a labelled leaning.
- **Doc brief**: carries the substance: what changed and why, the D-nnn and OD-nn involved, the
  reader (the EDS, the LDS or a future user), and the §8 style (verdict first, one owner per fact,
  edit in place, roles only, no flowcharts). The agent writes; it doesn't decide what is true.

## 5. Spawn

- Spawn every independent agent in one message; they run in the background by default. Don't
  poll; the result arrives as a notification.
- Long shell jobs (data generation, slow tests) run in the background meanwhile.
- One memory-heavy job at a time (local Spark, the full test suite): the 8 GB Mac is the limit.
- A subagent's prompt cache lasts five minutes, so a wait or a command past that re-writes its
  whole context. Subagents run no Spark and no command over about four minutes; the main thread
  runs those in one batch per wave. A hook keeps the Mac awake while agents work, and the lid
  stays open (`docs/context/lessons.md`, T41).
- The review subagents run together, in one message, once the merged state passes its tests and
  `ruff`. They run no tests themselves beyond those of the files under review.
- A subagent can spawn its own subagents, three levels deep. Hand a whole minor step to one
  orchestrating subagent when the main thread would otherwise hold many small results.

## 6. Integrate and verify

1. Read every result yourself. A report is a claim until the main thread has seen the diff.
2. Run the tests of the touched modules and `ruff check` on the touched files, and read fresh
   output (`verification-before-completion`). The full suite runs only when a major step or a
   multi-module build is finished, on the main thread in the background (D-072 (m)).
3. Run the reviewers in parallel: `code-reviewer` always, the §10 specialists whose trigger
   applies, and `simplicity-review` on code. Fix or explicitly justify every finding.
4. Read every doc diff in full against §8 before the EDS sees it: verdict first, one owner per
   fact, edited in place, nothing restated, roles only. A doc the EDS has to rewrite cost more
   than it saved.
5. Docs per §8 (`doc-sync`).
6. Checkpoint. End the minor step by writing `worknotes/handovers/<topic>.md` (state, decisions
   not yet in a repo file, running agents, next step) as the last tool call, after the log line.
   Auto-compaction is let through only there, and the checkpoint is added back after it, so the
   main thread stays small across a long build without losing what matters (D-072 (p),
   `.claude/hooks/compact_gate.py`).

## 7. Report to the EDS

One line per piece: what was delegated to which agent, model and effort, what came back, what the
main thread changed. Then what to review first and the open risks.

## Anti-patterns

- Planning the pieces and then doing them yourself.
- A design question sent out as research ("which sampling method should we use?").
- A cheaper model writing what the EDS or LDS reads as the record.
- `general-purpose` for a piece a worker agent covers, or a review agent with no `effort`.
- Vague briefs ("improve the tests", "clean this up").
- Two agents on one file.
- Forcing every agent to one model, or letting every agent inherit Fable.
- The full suite run by every agent, or for a small, targeted fix.
- Resuming a failed worker with the same brief; fix the brief first.
- Spawning for a single small edit; the overhead costs more than it saves.

## In this repo

- Precedent: the synthetic data generator, built in one go as independent stages with independent
  checks (`synthetic/REVIEW.md`).
- Agents live in `.claude/agents/`; a new or changed file is picked up within seconds. Each sets
  `autoCompactWindow: 1000000`, so the 300k window applies to the main thread only: a subagent
  has no checkpoint to compact at.
- `/efficiency` reports where the tokens went. Run it after each major step and give the EDS the
  Fable share and the cache rewrites (D-072 (q)).
- Nothing a subagent writes is done until the main thread has verified it (§1 workflow).
