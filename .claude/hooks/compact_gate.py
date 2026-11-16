"""Let auto-compaction through only right after a checkpoint, and hand the checkpoint back.

Claude Code runs this file as two hooks (`.claude/settings.json`):

- `PreCompact`, trigger `auto`: the main thread's context has passed the auto-compact window.
  Compacting loses nothing that matters only when the main thread's last tool-using response
  wrote a handover (`worknotes/handovers/<topic>.md`), because the state of the work is then on
  disk. Anywhere else this blocks (exit code 2) and the context keeps growing until the next
  checkpoint or the ceiling. A manual `/compact` and a subagent's compaction are never blocked.
- `SessionStart`, source `compact`: prints that handover, which Claude Code adds to the compacted
  context.

The gate holds a compaction back only when it is sure it is safe to: the model has a 1M-token
window and the context is well below it. Whatever it cannot read (an unknown model, an empty
transcript tail, a crash) lets the compaction through, which is what happens without this hook.

The hook input arrives as JSON on stdin and names the session's transcript (`.jsonl`). One
response is stored as several lines that share `message.id`, one per content block.
"""

import json
import sys
from pathlib import Path

CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "worknotes" / "handovers"
# Models with a 1M-token window. On any other model the gate stands aside.
LARGE_WINDOW_MODELS = ("claude-fable-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5-5")
# Tokens, measured on the last request: leaves room for one very large turn before the window ends.
CONTEXT_CEILING = 600_000
TAIL_BYTES = 4_000_000  # of the transcript: holds the last response and its tool results

SUMMARY_INSTRUCTIONS = """The main thread has just written its checkpoint to {checkpoint}, and \
that file is added back in full after this compaction. Do not repeat what it says. Keep in the \
summary only what it cannot hold: instructions and decisions the user gave in this session that \
are not yet in a repo file, every background agent still running (name, id, what it is doing and \
what to do with its result), and what the main thread was about to do next."""


def read_tail(transcript_path: str) -> list[dict]:
    """Return the main thread's assistant and user records in the transcript's tail, in order."""
    with open(transcript_path, "rb") as f:
        f.seek(0, 2)
        start = max(0, f.tell() - TAIL_BYTES)
        f.seek(start)
        lines = f.read().decode("utf-8", errors="replace").split("\n")
    # The seek may land inside a line, and the last line may still be being written.
    lines = lines[1 if start else 0 : -1]
    records = []
    for line in lines:
        if '"type":"assistant"' not in line and '"tool_result"' not in line:
            continue
        record = json.loads(line)
        if record.get("type") in ("assistant", "user") and not record.get("isSidechain"):
            records.append(record)
    return records


def measure_context(records: list[dict]) -> tuple[int, str]:
    """Return the context size in tokens and the model of the main thread's last request."""
    for record in reversed(records):
        message = record["message"]
        usage = message.get("usage")
        if record["type"] == "assistant" and usage and message.get("model") != "<synthetic>":
            size = (
                usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0)
            )
            return size, message.get("model", "")
    return 0, ""


def find_failed_calls(records: list[dict]) -> set[str]:
    """Return the ids of the tool calls whose result came back as an error."""
    failed = set()
    for record in records:
        content = record["message"].get("content")
        if record["type"] != "user" or not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_result" and block.get("is_error"):
                failed.add(block["tool_use_id"])
    return failed


def find_checkpoint(records: list[dict]) -> str | None:
    """Return the handover that the main thread's last tool-using response wrote, else None."""
    failed = find_failed_calls(records)
    last_id = None
    for record in reversed(records):
        if record["type"] != "assistant":
            continue
        message = record["message"]
        calls = [b for b in message.get("content", []) if b.get("type") == "tool_use"]
        if last_id is None and calls:
            last_id = message["id"]
        if last_id is not None and message["id"] != last_id:
            break
        for call in calls:
            path = Path(call["input"].get("file_path", ""))
            wrote = call["name"] in ("Write", "Edit") and call["id"] not in failed
            if wrote and path.parent == CHECKPOINT_DIR and path.suffix == ".md":
                return str(path)
    return None


def gate_compaction(hook_input: dict) -> int:
    """Decide one compaction: 0 lets it through, 2 blocks it."""
    if hook_input.get("trigger") != "auto" or hook_input.get("agent_id"):
        return 0
    records = read_tail(hook_input["transcript_path"])
    checkpoint = find_checkpoint(records)
    if checkpoint:
        print(SUMMARY_INSTRUCTIONS.format(checkpoint=checkpoint))
        return 0
    context, model = measure_context(records)
    if not model.startswith(LARGE_WINDOW_MODELS) or context >= CONTEXT_CEILING:
        return 0
    print(
        f"Auto-compaction held back at {context:,} tokens: the main thread's last tool calls "
        f"wrote no checkpoint. It goes through right after a handover is written to "
        f"{CHECKPOINT_DIR.name}/, or at {CONTEXT_CEILING:,} tokens.",
        file=sys.stderr,
    )
    return 2


def print_checkpoint(hook_input: dict) -> int:
    """Print the handover written right before a compaction, for the compacted context."""
    checkpoint = find_checkpoint(read_tail(hook_input["transcript_path"]))
    if checkpoint and Path(checkpoint).exists():
        print(
            f"Checkpoint written right before this compaction ({checkpoint}). It is the state "
            "of the work; the repo files it names are the source of truth.\n"
        )
        print(Path(checkpoint).read_text(encoding="utf-8"))
    return 0


def main() -> int:
    """Run the hook that the input names."""
    hook_input = json.load(sys.stdin)
    if hook_input["hook_event_name"] == "PreCompact":
        return gate_compaction(hook_input)
    return print_checkpoint(hook_input)


if __name__ == "__main__":
    sys.exit(main())
