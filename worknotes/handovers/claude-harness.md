# Handover: claude-harness
_Written: 2026-11-16 · branch: main · last commit: fa84160 (everything below is uncommitted)_

## Goal
The EDS asked which agents, skills or mods would help, whether the third-party plugin Chisle is
worth installing, and whether the orchestration is efficient: "I never really get feedback
whether something could have been done more efficiently, better, less tokens". After the
measurement they said "do these steps" (six) and asked two things: can auto-compaction be
triggered only where it is effectively lossless, and can the unrelated plugins be turned off for
this repo only.

## State (done, uncommitted, not yet reviewed by the EDS)
Measurement (all transcripts, 30 Sep to 16 Nov, list prices as one unit): about $2,300; cache
writes 47%, cache reads 29%, output 24%; subagents 53%; Fable 34%. Whole-context cache rewrites
23%, the largest group the Mac sleeping under background subagents (T41: 248 rewrites, about
11%, about 65 agent-hours stalled). 58% of main-thread requests above 300k context.

1. **Keep-awake:** `.claude/hooks/keep_awake.sh`, a `PreToolUse` hook on every tool call, async.
   Verified live: it fired by itself and `pmset -g assertions` shows the assertion held.
2. **Worker agents:** `.claude/agents/builder.md`, `researcher.md`, `doc-writer.md` (tools, model
   and effort pinned). `delegation` §3 to §6 route to them and the brief template is shorter.
   Not yet used for a real piece.
3. **Feedback loop:** `/efficiency` (`.claude/commands/efficiency.md`) runs
   `.claude/scripts/session_usage.py` (395 lines, ported by a Sonnet subagent; its totals
   reconcile with the scratch analysis). No status line: the VS Code extension shows context by
   itself, and the docs do not say a status line renders there.
4. **Effort:** `~/.claude/settings.json`, all four models from `xhigh` to `high`.
5. **Lossless-only compaction:** `.claude/hooks/compact_gate.py` as `PreCompact` (auto) and
   `SessionStart` (compact); `autoCompactWindow: 300000` and `precomputeCompactionEnabled: false`
   in `.claude/settings.json`; all seven agent files set `autoCompactWindow: 1000000`. The gate
   lets an auto-compaction through only when the main thread's last tool-using response wrote a
   handover, or at 600k tokens, or on a model it does not know to have a 1M window. 14
   constructed cases pass. **Not yet seen end to end:** in the session that built it, no
   compaction was attempted at about 500k after this checkpoint was written. The likely cause
   is that `autoCompactWindow` is read at session start (the docs do not say). Check in the
   next new chat: `/autocompact` with no argument shows the active window.
6. **Plugins:** `.claude/settings.local.json` (gitignored) with `syncClaudeAiPlugins: false` and
   `disableClaudeAiConnectors: true`. Takes effect in a new chat or after `/reload-plugins`:
   not yet observed.

Docs changed: `CLAUDE.md` §1, §8, §10, §12; D-072 (o) to (q); `lessons.md` T41;
`docs/guides/skills_and_agents.md`, `claude_code_workflow.md`, `setup_windows_wsl2.md`;
`worknotes/README.md`; the `/handover` command; `worknotes/log.md`; the memory note
`project-mac-sleep-stalls-agents`.

Code review: one `code-reviewer` (Opus, high) on the two hooks and the script found 2 blocking
defects in the gate (a fixed ceiling that could block the compaction that rescues a full
context), 5 should-fix and several nits. All fixed and re-tested, except two left on purpose:
two parallel tool calls can each start a `caffeinate` (harmless, commented), and
`summarise_sessions` sorts by column position.

## Decisions in that chat
In D-072 (o) to (q). Also: Chisle is not installed (it cuts the middle out of Bash and agent
output over 8,000 characters, which reviewers here read in full). Subagents keep the 5-minute
cache: `subagentPromptCacheTtl: "1h"` exists, but 1-hour writes cost 2x against 1.25x and with
the Mac awake it does not pay.

Settled by the EDS on 2026-11-16: all claude.ai connectors stay off in this repo; the essence of
the four never-loaded skills (`bank-parity-check`, `systematic-debugging`,
`verification-before-completion`, `new-component`) is folded into the `builder` prompt, and the
verification and root-cause rules into `CLAUDE.md` §9, because their guidance must be applied;
no commit. Also settled that day:
- Progress visibility (D-072 (r)): a "Keep the EDS posted" rule in `CLAUDE.md` §9 and
  `showThinkingSummaries: true` in the user settings (effective from the next chat, after a
  window reload). Claude Code already requests progress updates from the API, so there is no
  `display` setting to change.
- The advisor tool (`/advisor fable` on an Opus session) stays off: every call re-reads the whole
  conversation uncached at the advisor's price and subagents inherit it. Revisit after the
  first `/efficiency` baseline.
- `prefix_mismatch_behavior: "drop_block"` does not apply: it is for harnesses that edit
  history, and Claude Code owns its requests.
- The four skill files stay as the long form.

Looked at for the EDS's learning, nothing changed: Managed Agents multiagent orchestration
(hosted agents on the Claude API, in beta). It is the hosted counterpart of what this repo
does locally with `.claude/agents/` and the Agent tool. It needs a Console account with API
billing and a key (the Mac has no key, no `anthropic` package and no `ant` CLI), and it bills
tokens at list price outside the subscription. Not proposed for this project.

## Open questions
None for the EDS. A known limit: the gate also holds back idle compaction in a conversation.
Remedy: `/handover <topic>` or a manual `/compact` before a long break.

## Running agents
None.

## Next steps
1. In the next new chat: run `/autocompact` to confirm the 300k window is active, and watch
   whether a compaction goes through after the first checkpoint past 300k.
2. After the next major step run `/efficiency` and compare with the baseline above.
3. If a real auto-compaction misbehaves, remove `autoCompactWindow` from `.claude/settings.json`;
   the gate then has nothing to gate.

## Gotchas
- The checkpoint must be in the last tool-using response. Any later tool call closes the gate
  until the next checkpoint.
- In `pmset -g log`, a `Wake  Requests` line is not a wake; only `Wake from` and `DarkWake from`.
- Loading the `claude-api` or `update-config` skill adds tens of thousands of tokens; ask the
  docs agent for the one fact instead.
- The measurement passes and the gate's test script are in the session scratchpad and will not
  survive it. `session_usage.py` is the part that was kept.

## Read first
`worknotes/log.md` (the 2026-11-16 entry), `docs/decisions.md` D-072 (o) to (q),
`docs/context/lessons.md` T41, `.claude/skills/delegation/SKILL.md`.
