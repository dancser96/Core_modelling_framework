# Working with Claude Code on this repo

**Verdict:** git is the only thing that syncs between machines. Claude Code sessions are local to
each machine, so continuity comes from `CLAUDE.md`, the committed docs (`docs/UPDATES.md`,
`docs/roadmap.md`, `docs/decisions.md`) and small, pushed commits, never from chat history. The
committed `worknotes/` add a sync page for you and the Lead DS, a verbose log and chat handovers
(`CLAUDE.md` §8). Where to start reading: `docs/README.md`.

## Surfaces

- **VS Code extension** (main surface on both machines): side panel, inline diffs, plan review.
- **CLI** (`claude` in the integrated terminal): the same agent, useful for quick tasks. It needs the
  separate CLI install from the setup guides; the extension doesn't add `claude` to your PATH.
- **Optional, when travelling:** Claude Code on the web (claude.ai/code) runs sessions against a
  fresh clone of the GitHub repo, and `claude --teleport` pulls a cloud session back locally. It is
  handy, but teleport has open bug reports, so don't make it your backbone.

## The loop for every task

1. `git pull`, then start a session in the repo root. Claude reads `CLAUDE.md` automatically and
   follows its §0 reading list (UPDATES, then roadmap / project / component docs as needed).
2. **Major step? Start wide.** For a new component, config section, public function or dependency,
   or anything you call a significant redesign or extension: "brainstorm this first". Claude
   researches best practice, critiques the ideas (yours and its own) and runs `holistic-review`
   across all components before planning. Answer its numbered questions by number.
3. **Plan first.** Ask for a plan (files, function names/signatures, what is left out). In the CLI,
   `Shift+Tab` cycles into plan mode. Approve or trim it; cutting scope here is the cheapest
   anti-slop step.
4. **Small steps.** One logical change per step. Review every diff line by line before accepting.
5. **Checks.** `pytest`, `ruff check .`, then "run the code-reviewer subagent on this diff". Add
   `silent-failure-hunter` / `ml-correctness-auditor` / `compat-guardian` when their triggers apply
   (`CLAUDE.md` §10). For bugs, "debug this systematically" runs `systematic-debugging`.
6. **Docs.** "Run doc-sync": component doc, UPDATES, decisions, roadmap open decisions, glossary, and
   the `worknotes/` sync page and log. Occasionally, `/revise-claude-md` captures session learnings
   into `CLAUDE.md` or the right doc.
7. **Commit and push** (one branch per task; merge when happy). The next machine picks up from git.

## Continuity between chats, days and machines

| Need | Use |
|---|---|
| Daily Lead DS sync (~1h): what to review, open questions, what to demo | `/brief` (refreshes `worknotes/sync.md`; the Lead DS can read it directly) |
| A context that has grown too big; continue in a new chat | `/handover <topic>`, then `/resume <topic>` in the new chat (one file per topic, so parallel topics are fine) |
| Where are we? | `docs/UPDATES.md` |
| What's next, and what's still undecided? | `docs/roadmap.md` (milestones, backlog, OD-nn) |
| Why did we decide X? | `docs/decisions.md` (D-nnn) |

`worknotes/` is committed: push it with the work so the Lead DS sees the sync page and handovers
resume on either machine.

## Prompts that work well here

- "Plan only, no code: how would you implement <X> within CLAUDE.md §1? List functions and
  signatures."
- "Show me the smallest version of this that satisfies the requirement. What did you leave out?"
- "Review this diff with the simplicity-review skill and fix only blocking findings."
- "What in this change could break an existing config or a public function?"
- "Holistic review: what else does this affect?"

## Context and usage

- `/clear` between unrelated tasks; `/compact` in long sessions, or `/handover` + a fresh chat when
  the context is bloated. Subagents keep reviews out of the main context.
- Opus-heavy sessions use up plan limits quickly. Keep tasks small, and use `/model` to drop to a
  lighter model for mechanical work (renames, doc edits). The subagents default to the session model
  (`model: inherit`); set them to `sonnet` in `.claude/agents/*.md` if usage becomes the bottleneck.

## Hard rules

- **Never** paste bank data, outputs, internal paths, table names or screenshots with internal
  identifiers into Claude or the repo. Describe structure in generic terms instead.
- Internal changes come back **as descriptions**. Claude re-implements them here, and the change is
  logged in `docs/UPDATES.md`.
- People are referred to by role (the Lead DS, the Chief DS), never by name, including in
  `worknotes/`.

## Releasing into the bank

1. Bump `__version__` (semver), update `docs/UPDATES.md`, commit, and tag `vX.Y.Z`.
2. GitHub → the tag → *Download ZIP*.
3. Copy the contents into the internal repo, then set `conf/local/` there (it is gitignored here and
   never leaves the bank).

The longer-term release path (internal CI, a package repository, version pins) is open: OD-04 in
`docs/roadmap.md`.
