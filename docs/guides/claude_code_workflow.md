# Working with Claude Code on this repo

**Verdict:** git is the only thing that syncs between machines. Claude Code sessions are local to
each machine, so continuity comes from `CLAUDE.md`, `docs/UPDATES.md` and small, pushed commits —
never from chat history.

## Surfaces

- **VS Code extension** (main surface on both machines): side panel, inline diffs, plan review.
- **CLI** (`claude` in the integrated terminal): the same agent, useful for quick tasks. It needs
  the separate CLI install from the setup guides; the extension doesn't add `claude` to your PATH.
- **Optional, when travelling:** Claude Code on the web (claude.ai/code) runs sessions against a
  fresh clone of the GitHub repo, and `claude --teleport` pulls a cloud session back locally. It is
  handy, but teleport has open bug reports — don't make it your backbone.

## The loop for every task

1. `git pull`, then start a session in the repo root. Claude reads `CLAUDE.md` automatically.
   Ask it to read `docs/UPDATES.md` and the relevant component doc.
2. **Plan first.** Ask for a plan (files, function names/signatures, what is left out). In the CLI,
   `Shift+Tab` cycles into plan mode. Approve or trim it — cutting scope here is the cheapest
   anti-slop step. For new or unsettled design, "brainstorm this first" runs the `brainstorming`
   skill before the plan.
3. **Small steps.** One logical change per step. Review every diff line-by-line before accepting.
4. **Checks.** `pytest`, `ruff check .`, then "run the code-reviewer subagent on this diff".
   Add `silent-failure-hunter` / `ml-correctness-auditor` / `compat-guardian` when their triggers
   apply (`CLAUDE.md` §10). For bugs, "debug this systematically" runs `systematic-debugging`.
5. **Docs.** "Run doc-sync" — component doc, `UPDATES.md`, decisions if any. Occasionally,
   `/revise-claude-md` captures session learnings into `CLAUDE.md` or the right doc.
6. **Commit and push** (one branch per task; merge when happy). The next machine picks up from git.

## Prompts that work well here

- "Plan only, no code: how would you implement <X> within CLAUDE.md §1? List functions and
  signatures."
- "Show me the smallest version of this that satisfies the requirement. What did you leave out?"
- "Review this diff with the simplicity-review skill and fix only blocking findings."
- "What in this change could break an existing config or a public function?"

## Context and usage (Pro plan)

- `/clear` between unrelated tasks; `/compact` in long sessions. Subagents keep reviews out of the
  main context.
- Opus-heavy sessions use up Pro limits quickly. Keep tasks small, and use `/model` to drop to a
  lighter model for mechanical work (renames, doc edits). The subagents default to the session
  model (`model: inherit`); set them to `sonnet` in `.claude/agents/*.md` if usage becomes the
  bottleneck. Max makes sense once Opus becomes the daily default.

## Hard rules

- **Never** paste bank data, outputs, internal paths, table names or screenshots with internal
  identifiers into Claude or the repo. Describe structure in generic terms instead.
- Internal changes come back **as descriptions**. Claude re-implements them here, and the change is
  logged in `docs/UPDATES.md`.

## Releasing into the bank

1. Bump `__version__` (semver), update `docs/UPDATES.md`, commit, and tag `vX.Y.Z`.
2. GitHub → the tag → *Download ZIP*.
3. Copy the contents into the internal repo, then set `conf/local/` there (it is gitignored here
   and never leaves the bank).
