# Skills and subagents

**Verdict:** skills and subagents don't make a strong model smarter. They make it follow *this
project's* procedures consistently, and they let a fresh-context reviewer catch what the author
missed. All of them live in the repo (`.claude/`), so every machine and any future collaborator
gets them through git.

## Which mechanism for what

| Mechanism | Loaded | Use for |
|---|---|---|
| `CLAUDE.md` | Every session, always | Rules that apply to everything (keep it lean) |
| Skill `.claude/skills/<name>/SKILL.md` | Only when relevant (matched by its description) or asked for by name | Repeatable procedures and checklists |
| Subagent `.claude/agents/<name>.md` | When delegated to; runs in its own fresh context | Independent review / audit without polluting the main context |

## Current inventory

| Kind | Name | Purpose |
|---|---|---|
| Skill | `simplicity-review` | Checklist review of a diff against the code-light rules |
| Skill | `doc-sync` | Applies the documentation update rules at the end of a task |
| Skill | `new-component` | Adds a new component with its doc, config section, tests and status row |
| Skill | `bank-parity-check` | Checks deps, imports and IO against the bank environment |
| Skill | `brainstorming` *(vendored)* | Clarifies intent and design before the CLAUDE.md plan step for new or unsettled work |
| Skill | `systematic-debugging` *(vendored)* | Root cause before any fix; one hypothesis at a time |
| Skill | `verification-before-completion` *(vendored)* | No "done" or "passing" claim without fresh command output |
| Skill | `claude-md-improver` *(vendored)* | Audits CLAUDE.md and routes findings per §8 |
| Command | `/revise-claude-md` *(vendored)* | Captures session learnings into CLAUDE.md or the right doc |
| Subagent | `code-reviewer` | Fresh-context review for simplicity, clarity, structure |
| Subagent | `ml-correctness-auditor` | Leakage, time separation, evaluation and calibration invariants |
| Subagent | `compat-guardian` | Forward compatibility: config schemas, public API, artifact formats |
| Subagent | `silent-failure-hunter` *(vendored)* | Swallowed exceptions, silent fallbacks, data coercion that hides failures |
| Plugin | `pyright-lsp` | Live Python type checking for Claude (enabled in `.claude/settings.json`; optional local `pyright`) |

Vendored items are adapted to this repo; sources, commits and local changes are in
`.claude/skills/SOURCES.md`.

**Deliberate exception to "everything lives in the repo":** Anthropic's `skill-creator` is used from
the user-level plugin (`/plugin install example-skills@anthropic-agent-skills`), not vendored. It is
~250KB with scripts that call `claude -p`, open a browser and load CDN assets: too heavy to review
and not something to ship in the bank zip. `pyright-lsp` is likewise a marketplace plugin, because
it is LSP configuration with no files to vendor.

## Anatomy

**Skill** — a folder with a `SKILL.md`:
```markdown
---
name: my-skill
description: What it does AND when to use it. Be specific and a little pushy — models tend to
  under-trigger skills. Mention the situations and keywords that should trigger it.
---
# Instructions (imperative, explain *why*, keep < ~500 lines)
```
Optional subfolders: `references/` (docs loaded on demand) and `scripts/` (only if genuinely
needed — scripts are code and fall under the code-light rules).

**Subagent** — one Markdown file with YAML frontmatter; the body is its system prompt:
```markdown
---
name: my-agent
description: When Claude should delegate to it.
tools: Read, Grep, Glob, Bash     # grant the minimum
model: inherit                    # or sonnet / opus / haiku
---
You are ... (role, checklist, output format)
```
Manage subagents with `/agents`. If a new one doesn't show up, restart Claude Code.

## Adding a skill or subagent (process)

1. Confirm it is a *repeated* procedure. One-offs belong in the prompt, not a skill.
2. Write it in `.claude/skills/<name>/SKILL.md` or `.claude/agents/<name>.md`. Anthropic's
   `skill-creator` skill (user-level plugin, see above) is a good authoring aid.
3. Test it: ask for a task that should trigger it and check that it does. Tighten the description if
   it doesn't.
4. Add it to the inventory above and commit.

## Candidate skills to add later (when the need is real)

| Skill | Add when |
|---|---|
| `config-migration` | The first `schema_version` bump |
| `eda-report` | The EDA report format is agreed |
| `use-case-onboarding` | Turning a business intake into a validated use-case config |
| `release-to-bank` | The first real release (version bump, tag, zip, internal copy checklist) |
| `test-hardening` | Pre-migration push to full coverage + Sonar readiness |
| `runtime-profiling` | Systematic runtime optimisation work starts |

## Pulling skills from other GitHub repos

Rule for this repo: **everything used lives in the repo.** Try external skills however you like,
but vendor what you keep.

- **Vendor (recommended).** Download or clone the source repo and copy the skill folder into
  `.claude/skills/<name>/`. Record the source URL, commit hash and license in
  `.claude/skills/SOURCES.md`. Then **read every file**: skills are instructions (and possibly
  scripts) that run with your permissions. Adapt it to this repo's rules, or drop it.
- **Plugin marketplace (try-out only).** In Claude Code:
  `/plugin marketplace add anthropics/skills`, then
  `/plugin install example-skills@anthropic-agent-skills`. Plugins install at user level, not in the
  repo — use this to evaluate, then vendor.
- **Third-party installers** such as `npx skills add <repo> --skill <name>` can drop skills into
  `.claude/skills/`. They are community tools; review what they write, exactly as with vendoring.

Never add a skill that fetches remote content or instructions at runtime.

**Sources worth knowing:** `anthropics/skills` (official examples, including `skill-creator`),
`anthropics/claude-plugins-official` (small single-purpose plugins whose agents and skills can be
vendored file by file), `obra/superpowers` (process skills; strongly opinionated, adapt before use).
Large all-in-one kits (e.g. ECC) are not a fit for this repo's code-light rules. Community
collections exist; treat them as unvetted until reviewed.
