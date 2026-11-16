---
description: Report where Claude Code tokens went on this repo (by model, thread, context size, cache rewrites and subagent) and what could have been cheaper
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--session <id prefix>], default: the last 7 days"
allowed-tools: Bash(python3 .claude/scripts/session_usage.py:*)
---

Run `python3 .claude/scripts/session_usage.py $ARGUMENTS` and report to the EDS in at most 25
lines. The figures are API list prices, used as one unit across models; they are not a bill.

1. **The total and its shares:** main thread against subagents; cache writes against cache reads
   against output; the Fable share against the 25–30% ceiling (D-072 (l)).
2. **Whole-context cache rewrites:** how many, their share of the spend, and what the largest
   group points to. Subagent rewrites after a 5–60 minute gap mean the machine slept or a command
   ran past five minutes (`docs/context/lessons.md`, T41). Main-thread rewrites after more than an
   hour mean a long context was resumed instead of handed over.
3. **Main-thread context:** the share of requests above 300k tokens, and the peak per session.
4. **The three costliest subagents:** for each, whether its piece could have been smaller, on a
   cheaper model, or at lower effort.
5. **One or two concrete changes** for the next major step. Say so plainly when nothing stands
   out.

Report what the output shows and do not estimate what it doesn't. Change nothing on the strength
of the report without the EDS's go.
