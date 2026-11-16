"""Report where Claude Code tokens went for this repo, read from its local transcripts.

Dev tool for the repo owner, run after a major build step to see whether the work could have been
cheaper. Standard library only. Run:

    python3 .claude/scripts/session_usage.py [--since YYYY-MM-DD] [--until YYYY-MM-DD]
        [--session <id prefix>] [--top N]

Every request is priced at API list prices as one unit across models; the total is not a bill.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

# List prices as of 2026-11-16 in $ per million tokens: input, output, cache read. A cache write
# costs 1.25x (5 minutes) or 2x (1 hour) the input price. Used as one unit across models.
PRICE = {
    "fable-5-2": (8.0, 40.0, 0.20),
    "fable-5-1": (10.0, 50.0, 0.25),
    "fable-5": (10.0, 50.0, 1.00),
    "opus-5-5": (4.0, 20.0, 0.20),
    "opus-5": (5.0, 25.0, 0.50),
    "sonnet-5-5": (2.0, 10.0, 0.10),
    "sonnet-5": (2.0, 10.0, 0.20),
    "haiku-5-5": (0.10, 0.50, 0.01),
    "haiku-4-5": (1.0, 5.0, 0.10),
}
WRITE_5M, WRITE_1H = 1.25, 2.0
CONTEXT_BUCKETS_K = [(0, 100), (100, 200), (200, 300), (300, 500), (500, 10**6)]
FABLE_TARGET = "target: at most 25-30%"


@dataclass
class Request:
    """One API request: its tokens, time and thread."""

    thread: str
    kind: str  # main, subagent or workflow
    session: str
    model: str
    time: datetime
    effort: str | None
    input: int
    cache_write_5m: int
    cache_write_1h: int
    cache_read: int
    output: int

    @property
    def context(self) -> int:
        """Context size: every input token, cached or not."""
        return self.input + self.cache_write_5m + self.cache_write_1h + self.cache_read

    @property
    def cache_write(self) -> int:
        """Tokens written to the cache."""
        return self.cache_write_5m + self.cache_write_1h

    @property
    def cost(self) -> dict[str, float]:
        """Dollars at list price by category: input, write, read, output."""
        p_in, p_out, p_read = PRICE[self.model]
        return {
            "input": self.input * p_in / 1e6,
            "write": (self.cache_write_5m * WRITE_5M + self.cache_write_1h * WRITE_1H) * p_in / 1e6,
            "read": self.cache_read * p_read / 1e6,
            "output": self.output * p_out / 1e6,
        }

    @property
    def usd(self) -> float:
        """Dollars at list price, all categories."""
        return sum(self.cost.values())


def find_transcript_dir() -> Path:
    """Locate this repo's Claude Code transcript folder, or stop with a clear message."""
    repo_root = Path(__file__).resolve().parents[2]
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(repo_root))
    folder = Path.home() / ".claude" / "projects" / slug
    if not folder.is_dir():
        raise SystemExit(f"No transcript folder for this repo at {folder}")
    return folder


def short_model(name: str) -> str:
    """Strip the claude- prefix and date suffix, giving a key of PRICE."""
    name = name.removeprefix("claude-")
    for key in sorted(PRICE, key=len, reverse=True):
        if name.startswith(key):
            return key
    raise ValueError(f"No list price for model {name!r}; add it to PRICE")


def read_usage(usage: dict) -> dict[str, int]:
    """Pick the token counts of one usage record; a missing cache breakdown counts as 5-minute."""
    breakdown = usage.get("cache_creation") or {}
    cache_write_5m = breakdown.get("ephemeral_5m_input_tokens", 0)
    if not breakdown:
        cache_write_5m = usage.get("cache_creation_input_tokens", 0)
    return {
        "input": usage.get("input_tokens", 0),
        "cache_write_5m": cache_write_5m,
        "cache_write_1h": breakdown.get("ephemeral_1h_input_tokens", 0),
        "cache_read": usage.get("cache_read_input_tokens", 0),
        "output": usage.get("output_tokens", 0),
    }


def read_thread_meta(path: Path, root: Path) -> dict:
    """Describe a transcript file: kind, session id and, for subagents, the .meta.json fields."""
    parts = path.relative_to(root).parts
    if len(parts) == 1:
        return {"kind": "main", "session": path.stem}
    meta_path = path.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    kind = "workflow" if "workflows" in parts else "subagent"
    return {"kind": kind, "session": parts[0], **meta}


def read_requests(root: Path) -> tuple[dict[str, Request], dict[str, dict]]:
    """Read every transcript into one Request per message id, plus the metadata of each thread."""
    requests: dict[str, Request] = {}
    threads: dict[str, dict] = {}
    for path in sorted(root.rglob("*.jsonl")):
        thread = threads[path.stem] = read_thread_meta(path, root)
        with path.open() as lines:
            # The live session's last line may still be being written: it has no newline yet.
            complete = [line for line in lines if line.endswith("\n")]
        for line in complete:
            record = json.loads(line)
            message = record.get("message") or {}
            if record.get("type") != "assistant" or message.get("model") in (None, "<synthetic>"):
                continue
            usage = read_usage(message.get("usage") or {})
            known = requests.get(message["id"])
            if known is None:
                requests[message["id"]] = Request(
                    thread=path.stem,
                    kind=thread["kind"],
                    session=thread["session"],
                    model=short_model(message["model"]),
                    time=datetime.fromisoformat(record["timestamp"]).astimezone(),
                    effort=record.get("effort"),
                    **usage,
                )
            elif known.thread == path.stem:  # streamed blocks repeat the usage; keep the maximum
                for field, value in usage.items():
                    setattr(known, field, max(getattr(known, field), value))
    return requests, threads


def filter_requests(
    requests: list[Request], since: date, until: date | None, session: str
) -> list[Request]:
    """Keep requests inside the period whose session id starts with the given prefix."""
    return [
        r
        for r in requests
        if r.time.date() >= since
        and (until is None or r.time.date() <= until)
        and r.session.startswith(session)
    ]


def group_threads(requests: list[Request]) -> dict[str, list[Request]]:
    """Group requests by thread, each thread in time order."""
    by_thread = defaultdict(list)
    for r in requests:
        by_thread[r.thread].append(r)
    return {tid: sorted(rs, key=lambda r: r.time) for tid, rs in by_thread.items()}


def name_cause(prev: Request, r: Request) -> str:
    """Name why a request rewrote the whole context, by precedence."""
    gap_minutes = (r.time - prev.time).total_seconds() / 60
    if r.context < 0.6 * prev.context:
        return "after compaction"
    if r.model != prev.model:
        return "model switch"
    if gap_minutes < 5:
        return "under 5 min"
    return "5-60 min" if gap_minutes <= 60 else "over 60 min"


def find_rewrites(by_thread: dict[str, list[Request]]) -> list[tuple[Request, str]]:
    """List requests (not first of their thread) that wrote at least half a big context anew."""
    rewrites = []
    for rs in by_thread.values():
        for prev, r in zip(rs, rs[1:], strict=False):
            if r.context >= 50_000 and r.cache_write >= 0.5 * r.context:
                rewrites.append((r, name_cause(prev, r)))
    return rewrites


def summarise_subagents(
    by_thread: dict[str, list[Request]],
    threads: dict[str, dict],
    rewrites: list[tuple[Request, str]],
) -> list[dict]:
    """One row per subagent or workflow thread, with cost, size and rewrite count."""
    rewrite_count = Counter(r.thread for r, _ in rewrites)
    rows = []
    for tid, rs in by_thread.items():
        if rs[0].kind == "main":
            continue
        meta = threads[tid]
        rows.append(
            {
                "day": str(rs[0].time.date()),
                "description": (meta.get("description") or "")[:48],
                "type": meta.get("agentType") or "?",
                "model": rs[0].model,
                "effort": meta.get("effort") or rs[0].effort or "unset",
                "requests": len(rs),
                "peak_k": max(r.context for r in rs) / 1000,
                "rewrites": rewrite_count[tid],
                "minutes": (rs[-1].time - rs[0].time).total_seconds() / 60,
                "usd": sum_usd(rs),
            }
        )
    return rows


def summarise_sessions(requests: list[Request]) -> list[list]:
    """One row per session, costliest first: days, main-thread size, main and subagent dollars."""
    by_session = defaultdict(list)
    for r in requests:
        by_session[r.session].append(r)
    rows = []
    for session, rs in by_session.items():
        main = [r for r in rs if r.kind == "main"]
        subs = [r for r in rs if r.kind != "main"]
        peak_k = max((r.context for r in main), default=0) / 1000
        days = (str(min(r.time for r in rs).date()), str(max(r.time for r in rs).date()))
        thread_count = len({r.thread for r in subs})
        rows.append(
            [session[:8], *days, len(main), peak_k, thread_count, sum_usd(main), sum_usd(subs)]
        )
    return sorted(rows, key=lambda row: -(row[6] + row[7]))


def format_cell(value: object) -> str:
    """Format one table cell: thousands separators, two decimals for floats."""
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def print_table(title: str, header: list[str], rows: list[list]) -> None:
    """Print a titled plain-text table, numbers right-aligned."""
    cells = [[format_cell(v) for v in row] for row in rows]
    widths = [max(len(c) for c in column) for column in zip(header, *cells, strict=True)]
    print(f"\n{title}")
    print("  ".join(h.ljust(w) for h, w in zip(header, widths, strict=True)))
    for row, cell_row in zip(rows, cells, strict=True):
        pairs = zip(row, cell_row, widths, strict=True)
        print(
            "  ".join(c.rjust(w) if isinstance(v, int | float) else c.ljust(w) for v, c, w in pairs)
        )


def show_models(requests: list[Request], total: float) -> None:
    """Print requests, tokens and dollars by model and thread kind."""
    groups = defaultdict(list)
    for r in requests:
        groups[(r.model, r.kind)].append(r)
    rows = [
        [
            m,
            k,
            len(rs),
            sum(r.input + r.cache_write for r in rs) / 1e6,
            sum(r.cache_read for r in rs) / 1e6,
        ]
        + [sum(r.output for r in rs) / 1e6, sum_usd(rs), 100 * sum_usd(rs) / total]
        for (m, k), rs in groups.items()
    ]
    header = ["model", "kind", "requests", "new in M", "cache read M", "output M", "$", "share %"]
    print_table("Model x thread kind", header, sorted(rows, key=lambda row: -row[6]))


def show_categories(requests: list[Request], total: float) -> None:
    """Print dollars by category for main and subagents, and the Fable share."""
    rows = []
    for label, is_main in (("main", True), ("subagents", False)):
        rs = [r for r in requests if (r.kind == "main") == is_main]
        rows.append([label] + [sum(r.cost[c] for r in rs) for c in ("write", "read", "output")])
    print_table("Dollars by category", ["threads", "cache write", "cache read", "output"], rows)
    fable = sum_usd([r for r in requests if r.model.startswith("fable")])
    print(f"Fable share of the total: {100 * fable / total:.0f}% ({FABLE_TARGET})")


def show_context_sizes(requests: list[Request]) -> None:
    """Print main-thread requests and dollars by context size."""
    main = [r for r in requests if r.kind == "main"]
    rows = []
    for low, high in CONTEXT_BUCKETS_K:
        rs = [r for r in main if low * 1000 <= r.context < high * 1000]
        rows.append([f"{low}-{high}k" if high < 10**6 else f"{low}k+", len(rs), sum_usd(rs)])
    print_table("Main-thread requests by context size", ["context", "requests", "$"], rows)


def show_rewrites(rewrites: list[tuple[Request, str]]) -> None:
    """Print whole-context cache rewrites by thread kind and cause."""
    groups = defaultdict(list)
    for r, cause in rewrites:
        groups[("main" if r.kind == "main" else "subagent", cause)].append(r)
    rows = [
        [
            kind,
            cause,
            len(rs),
            sum(r.cache_write for r in rs) / 1e6,
            sum(r.cost["write"] for r in rs),
        ]
        for (kind, cause), rs in groups.items()
    ]
    header = ["threads", "cause", "count", "cache write M", "$"]
    title = "Whole-context cache rewrites (not the first request of a thread)"
    print_table(title, header, sorted(rows, key=lambda row: -row[4]))


def show_agent_types(subagents: list[dict]) -> None:
    """Print subagents by agent type, model and effort, at most 12 rows."""
    groups = defaultdict(list)
    for s in subagents:
        groups[(s["type"], s["model"], s["effort"])].append(s)
    rows = []
    for key, g in groups.items():
        total = sum(s["usd"] for s in g)
        rows.append([*key, len(g), total, total / len(g), sum(s["rewrites"] for s in g)])
    header = ["agent type", "model", "effort", "agents", "$", "$ per agent", "rewrites"]
    print_table("Subagents by type, model, effort", header, sorted(rows, key=lambda r: -r[4])[:12])


def show_top_subagents(subagents: list[dict], top: int) -> None:
    """Print the costliest subagents."""
    columns = ["day", "description", "type", "model", "effort", "requests", "peak_k"]
    columns += ["rewrites", "minutes", "usd"]
    ranked = sorted(subagents, key=lambda s: -s["usd"])[:top]
    header = [c.replace("_k", " k").replace("usd", "$") for c in columns]
    print_table(f"The {top} costliest subagents", header, [[s[c] for c in columns] for s in ranked])


def sum_usd(requests: list[Request]) -> float:
    """Dollars at list price for a group of requests."""
    return sum(r.usd for r in requests)


def parse_args() -> argparse.Namespace:
    """Read the command line options."""
    parser = argparse.ArgumentParser(description="Report where Claude Code tokens went.")
    default_since = date.today() - timedelta(days=7)
    parser.add_argument("--since", type=date.fromisoformat, default=default_since)
    parser.add_argument("--until", type=date.fromisoformat, default=None)
    parser.add_argument("--session", default="", help="session id prefix (default: all)")
    parser.add_argument("--top", type=int, default=8, help="how many costliest subagents to list")
    return parser.parse_args()


def main() -> None:
    """Read the transcripts, filter them and print the report."""
    args = parse_args()
    all_requests, threads = read_requests(find_transcript_dir())
    requests = filter_requests(list(all_requests.values()), args.since, args.until, args.session)
    if not requests:
        raise SystemExit("No requests in that period and session.")
    by_thread = group_threads(requests)
    rewrites = find_rewrites(by_thread)
    subagents = summarise_subagents(by_thread, threads, rewrites)
    total = sum_usd(requests)
    print(
        f"Period {args.since} to {args.until or 'today'}: {len(requests):,} requests, "
        f"{len(by_thread):,} threads, ${total:,.0f} at list price "
        "(list prices, a common unit across models, not a bill)"
    )
    show_models(requests, total)
    show_categories(requests, total)
    show_context_sizes(requests)
    show_rewrites(rewrites)
    show_agent_types(subagents)
    show_top_subagents(subagents, args.top)
    header = ["session", "first", "last", "main requests", "peak main k", "subagents"]
    sessions = summarise_sessions(requests)[:8]
    print_table("Costliest sessions", header + ["$ main", "$ subagents"], sessions)


if __name__ == "__main__":
    main()
