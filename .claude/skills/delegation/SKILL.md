---
name: delegation
description: Split a task into parallel subagent work, route each piece to the model and effort that match the cost of a wrong answer, and brief every agent completely. Use at the start of every non-trivial task (anything with two or more independent pieces of research, review, code, tests or docs), when implementation of an approved CLAUDE.md §1 plan starts, when running the review subagents, and whenever a task needs more than a few tool calls of searching or reading. Skip it only for a single small edit.
when_to_use: Trigger phrases include "delegate", "in parallel", "subagents", "split this up", "fan out", "orchestrate", "use a cheaper model", "use sonnet / haiku for", "run the reviews", "build these at once". Also any plan with several minor steps, any review round, any research question, any audit.
---

# Delegation

Work runs in parallel by default (D-071, `CLAUDE.md` §1 workflow). The main thread's context is
the scarce resource: it holds the plan, the SDS's decisions and the integration. Everything that
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
integration, and the conversation with the SDS. Don't do the pieces yourself after planning
them; that is the usual failure.

## 2. Research is not design

Research gathers and checks evidence: what is true, which options exist, what others do and with
what results, each with a source. Design decides what this repo does: it weighs that evidence
against the goals, the decision log, the constraints and the SDS's view. Brainstorming, the plan
and every choice between options are design, and design never leaves the main thread.

- A research brief asks "what is true?" or "what are the options and their evidence?", never
  "what should we do?".
- A researcher may add a leaning, labelled as one. The main thread decides, with the SDS.
- Inside `brainstorming`, the research step can be delegated; the critique and the design can't.

## 3. Route

Route by the cost of a wrong answer and how cheaply it can be checked, not by how small the piece
looks. A cheaper model takes only mechanical work that a test, a command or the main thread
reading the whole diff checks in full. Anything that feeds a decision, anything the SDS or LDS
reads as the record, and anything touching §4 runs on a strong model.

- **Strong** means the session model when it is Opus or Fable; otherwise pass `model: opus`.
- **Always pass `effort`** on the `Agent` call. What a subagent runs at without one isn't
  documented, and the default for Opus 5.5, Sonnet 5.5 and Haiku 5.5 is `medium`.
- Never set `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` or `CLAUDE_CODE_EFFORT_LEVEL`: they override every
  agent, the auditors included.

**Research**

| Piece | Agent type | Model, effort |
|---|---|---|
| Locate: where something lives in the repo or on a docs site | `Explore` | haiku, low |
| Fact check: one API or behaviour in the pinned version, quoting `file:line` of the installed package or the tagged source | `general-purpose` | sonnet, high |
| Fact check that traces behaviour through several code paths or libraries | `general-purpose` | strong, high |
| Best practice and literature: options and their evidence (§1 step 0, `brainstorming`) | `general-purpose` | strong, high; xhigh for a major step |

**Code and tests**

| Piece | Agent type | Model, effort |
|---|---|---|
| Mechanical change: rename, move, apply an established pattern | `general-purpose` | sonnet, medium |
| A minor step from a complete brief, with the signatures given | `general-purpose` | sonnet, high |
| Code in Target Factory, dataset and splits, features, training, calibration, evaluation or inference, or any §4 path | `general-purpose` | strong, high |
| Tests for a specified function | `general-purpose` | sonnet, high |
| Tests for a §4 invariant or a §2 migration path | `general-purpose` | strong, high |

**Docs.** They are how the SDS and the LDS see the work, so the cheaper model only propagates
text whose substance is already settled.

| Piece | Agent type | Model, effort |
|---|---|---|
| Propagation: a renamed term, cross-references, index and inventory rows, text the main thread wrote | `general-purpose` | sonnet, medium |
| Component doc content: a design section or a three-level rewrite, from substance given in the brief | `general-purpose` | strong, high |
| `worknotes/sync.md` and `log.md`, `docs/decisions.md` rows, OD rows, `docs/UPDATES.md`, review guides, the report to the SDS | main thread | session |

**Reviews and design**

| Piece | Agent type | Model, effort |
|---|---|---|
| `code-reviewer`, `silent-failure-hunter`, `compat-guardian` | that agent | strong, high |
| `ml-correctness-auditor` | that agent | strong, xhigh |
| Design, the plan, choices between options, integration | main thread | session |

Escalate a piece to a strong model when it turns out to need judgement, or when a cheaper attempt
failed once. Never retry the same brief on the same model. A cheaper model's output isn't done
until the main thread has read it in full and a strong reviewer has seen it (step 6).

## 4. Brief

Every brief has these parts, in this order. Short is fine; missing is not.

1. **Goal**: one sentence, plus why, so the agent can make the small calls itself.
2. **Read first**: the exact files and sections: `CLAUDE.md` §1 and the relevant §, the component
   doc, the trap numbers in `docs/context/lessons.md`, the legacy reference if any.
3. **Files you own**, and files you must not touch.
4. **Constraints**: the §1 rules in one line (functions first, ≤ ~50 lines, type hints and a
   docstring on every function, names from `docs/glossary.md`, fail loud, no new dependency, no
   bank names, no cwd-relative paths), plus the function names and signatures from the plan.
5. **Acceptance**: the commands to run and the expected result (`pytest tests/test_x.py`,
   `ruff check <files>`). The agent runs them and reports the output, not a claim.
6. **Report format**: at most ~15 lines: files and functions changed, the tail of the test and
   ruff output, open questions. No pasted files, no narrative.
7. **Stop rule**: if a constraint can't be met or something unexpected appears, stop and report;
   never work around it.

Two variants:
- **Research brief**: parts 3–5 become the question (what is true, or what the options are), the
  pinned version to check against, and where to look first. The report gives the evidence with
  sources, conflicts between sources, what is unverified, and at most a labelled leaning.
- **Doc brief**: carries the substance: what changed and why, the D-nnn and OD-nn involved, the
  reader (the SDS, the LDS or a future user), and the §8 style (verdict first, one owner per fact,
  edit in place, roles only, no flowcharts). The agent writes; it doesn't decide what is true.

## 5. Spawn

- Spawn every independent agent in one message; they run in the background by default. Don't
  poll; the result arrives as a notification.
- Long shell jobs (data generation, slow tests) run in the background meanwhile.
- One memory-heavy job at a time (local Spark, the full test suite): the 8 GB Mac is the limit.
- The review subagents run together, in one message, once the merged state passes `pytest` and
  `ruff`.
- A subagent can spawn its own subagents, three levels deep. Hand a whole minor step to one
  orchestrating subagent when the main thread would otherwise hold many small results.

## 6. Integrate and verify

1. Read every result yourself. A report is a claim until the main thread has seen the diff.
2. Run `pytest` and `ruff check .` on the merged state and read fresh output
   (`verification-before-completion`).
3. Run the reviewers in parallel: `code-reviewer` always, the §10 specialists whose trigger
   applies, and `simplicity-review` on code. Fix or explicitly justify every finding.
4. Read every doc diff in full against §8 before the SDS sees it: verdict first, one owner per
   fact, edited in place, nothing restated, roles only. A doc the SDS has to rewrite cost more
   than it saved.
5. Docs per §8 (`doc-sync`).

## 7. Report to the SDS

One line per piece: what was delegated to which agent, model and effort, what came back, what the
main thread changed. Then what to review first and the open risks.

## Anti-patterns

- Planning the pieces and then doing them yourself.
- A design question sent out as research ("which sampling method should we use?").
- A cheaper model writing what the SDS or LDS reads as the record.
- Omitting `effort`, so the agent runs at a level nobody chose.
- Vague briefs ("improve the tests", "clean this up").
- Two agents on one file.
- Forcing every agent to one model.
- Resuming a failed worker with the same brief; fix the brief first.
- Spawning for a single small edit; the overhead costs more than it saves.

## In this repo

- Precedent: the synthetic data generator, built in one go as independent stages with independent
  checks (`synthetic/REVIEW.md`).
- Agents live in `.claude/agents/`; a new one needs a session restart. If dedicated worker agents
  are added there, route to them instead of `general-purpose` plus `model`.
- Nothing a subagent writes is done until the main thread has verified it (§1 workflow).
