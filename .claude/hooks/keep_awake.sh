#!/bin/sh
# Keep the Mac awake for an hour after the latest Claude activity.
#
# Why: when the display turns off, macOS idle-sleeps within seconds although
# background subagents are still working, then wakes for a few seconds about
# every 16 minutes. Every wake costs each running subagent a whole-context cache
# rewrite, and a build that needs one hour takes twelve (docs/context/lessons.md, T41).
# The lid must stay open: closing it sleeps the Mac whatever this does.
# Does nothing where `caffeinate` does not exist (Linux, WSL).
command -v caffeinate >/dev/null 2>&1 || exit 0

# This runs on every tool call, so restart the timer at most every five minutes.
stamp="${TMPDIR:-/tmp}/claude_keep_awake.stamp"
[ -n "$(find "$stamp" -mmin -5 2>/dev/null)" ] && exit 0
touch "$stamp"

# Two parallel tool calls can each start one; both end within the hour, which is harmless.
pkill -fx "caffeinate -i -t 3600" 2>/dev/null
# stdin from /dev/null: caffeinate must not hold the pipe the hook input arrives on.
nohup caffeinate -i -t 3600 </dev/null >/dev/null 2>&1 &
