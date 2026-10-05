# Skill, agent and command sources

All skills, agents and commands under `.claude/` are authored for this repo unless listed below.
When vendoring a third-party one, add a row and review every file first.

| Item | Source repo | Commit | License | Reviewed / date | Local changes |
|---|---|---|---|---|---|
| `agents/silent-failure-hunter.md` | anthropics/claude-plugins-official (`plugins/pr-review-toolkit/agents/`) | `d182ca4` | Apache-2.0 | Claude, 2026-10-05 | Rewritten around §1 rule 8; read-only tools; dropped another project's Sentry/Statsig/`errorIds` specifics and user-facing UI checks; added pandas/Spark hidden-failure patterns |
| `skills/claude-md-improver/` | anthropics/claude-plugins-official (`plugins/claude-md-management/`) | `d182ca4` | Apache-2.0 | Claude, 2026-10-05 | Dropped `references/templates.md`; `.claude.local.md` → `CLAUDE.local.md`; removed `#` shortcut tip; added "In this repo" routing per §8 |
| `commands/revise-claude-md.md` | anthropics/claude-plugins-official (`plugins/claude-md-management/`) | `d182ca4` | Apache-2.0 | Claude, 2026-10-05 | `CLAUDE.local.md` filename; learnings routed per §8 |
| `skills/verification-before-completion/` | obra/superpowers | `8ca22db` | MIT | Claude, 2026-10-05 | Added this repo's minimum evidence (`pytest`, `ruff`, §1 review) |
| `skills/systematic-debugging/` | obra/superpowers | `8ca22db` | MIT | Claude, 2026-10-05 | Kept `SKILL.md` + `root-cause-tracing.md`; dropped skill-test, creation-log, JS timing and `find-polluter.sh` files and `defense-in-depth.md` (conflicts with boundary validation); fixed cross-refs; added "In this repo" section |
| `skills/brainstorming/` | obra/superpowers | `8ca22db` | MIT | Claude, 2026-10-05 | Softer trigger; specs go to `docs/components/` + `decisions.md`, no auto-commit; hands off to the CLAUDE.md §1 plan instead of `writing-plans`; dropped the visual companion (Node server) and spec-reviewer prompt |

Plugins enabled in `.claude/settings.json` (not vendored, updated by the official marketplace):
`pyright-lsp@claude-plugins-official` — LSP config only, needs a local `pyright` binary.
