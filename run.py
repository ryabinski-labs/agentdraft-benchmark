"""AgentDraft public collision benchmark.

Runs K rounds of N AI scheduling agents racing for the same calendar
slot through AgentDraft's conflict engine, then emits a machine-readable
JSON report and a human-readable Markdown report. Re-runnable on any
schedule, against any AgentDraft deployment.

This is the measurement instrument behind the claim: "We let N AI
scheduling agents fight over one calendar. Here's what happened." It is a
black-box HTTP client — it talks to a running AgentDraft API over the
public SDK and never imports server internals.

Quickstart — against the hosted API (recommended):

    pip install -r requirements.txt

    # Get free agent keys: sign up at https://agentdraft.io (Developer
    # tier, no card), create N agents with distinct priorities, then:
    AGENTDRAFT_BASE_URL=https://api.agentdraft.io \\
    AGENTDRAFT_API_KEYS=avs_live_aaa,avs_live_bbb,avs_live_ccc \\
      python run.py --rounds 100

    # ...or pass keys explicitly (lowest --api-key index = highest priority):
    python run.py --base-url https://api.agentdraft.io \\
      --api-key avs_live_aaa --api-key avs_live_bbb --api-key avs_live_ccc

Against your own AgentDraft instance (dev mode), the harness can
auto-provision agents via the magic-link bootstrap — no keys needed:

    python run.py --base-url http://127.0.0.1:8080 --rounds 100 --agents 5

Outputs land in ./out/ by default:

    benchmark-<UTC-date>.json   raw per-round results + aggregates
    benchmark-<UTC-date>.md     human-readable report
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import httpx

from agentdraft import Client, Conflict
from agentdraft.errors import AgentDraftError

REPO_ROOT = Path(__file__).resolve().parent

# Default agent names, in priority order (index 0 = rank 1 = highest).
NAMES = [
    "sales-bot",
    "recruit-bot",
    "focus-blocker",
    "exec-ea",
    "ops-bot",
    "support-bot",
    "growth-bot",
]


@dataclass
class Result:
    """One agent's result in a single race round."""

    agent_name: str
    agent_rank: int
    elapsed_ms: float
    status: str  # "201" | "409" | "error"
    detail: str
    booking_id: str | None
    winning_agent: str | None
    winning_priority: int | None


def fire_one(
    name: str,
    key: str,
    rank: int,
    base: str,
    start: datetime,
    end: datetime,
    t0: float,
) -> Result:
    c = Client(api_key=key, base_url=base, timeout=10.0)
    try:
        b = c.bookings.commit(
            start=start, end=end, idempotency_key=f"bench-{name}-{int(t0 * 1000)}"
        )
        return Result(
            agent_name=name,
            agent_rank=rank,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            status="201",
            detail="COMMITTED",
            booking_id=b.booking_id,
            winning_agent=None,
            winning_priority=None,
        )
    except Conflict as e:
        return Result(
            agent_name=name,
            agent_rank=rank,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            status="409",
            detail=getattr(e, "reason", "outranked"),
            booking_id=None,
            winning_agent=e.winning_agent_id,
            winning_priority=e.winning_agent_priority,
        )
    except AgentDraftError as e:
        return Result(
            agent_name=name,
            agent_rank=rank,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            status="error",
            detail=str(e),
            booking_id=None,
            winning_agent=None,
            winning_priority=None,
        )
    finally:
        c.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run the AgentDraft public collision benchmark.",
    )
    p.add_argument("--rounds", type=int, default=100, help="number of race rounds (default 100)")
    p.add_argument(
        "--agents",
        type=int,
        default=5,
        help="agents per round when auto-provisioning (ignored if --api-key/AGENTDRAFT_API_KEYS given)",
    )
    p.add_argument(
        "--api-key",
        action="append",
        default=None,
        dest="api_keys",
        help="an AgentDraft agent key; repeat for multiple agents (first = highest priority). "
        "Overrides auto-provisioning. May also be set via AGENTDRAFT_API_KEYS (comma-separated).",
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("AGENTDRAFT_BASE_URL", "http://127.0.0.1:8080"),
        help="AgentDraft API base URL (env: AGENTDRAFT_BASE_URL)",
    )
    p.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "out"),
        help="directory to write reports into",
    )
    p.add_argument(
        "--label",
        default="default-stack",
        help="short label for this run — appears in the report (e.g. 'agentdraft-prod')",
    )
    return p.parse_args()


def agents_from_keys(keys: list[str]) -> list[tuple[str, str, int]]:
    """Build the [(name, api_key, rank)] list from explicit keys.

    The first key is treated as rank 1 (highest priority), the second as
    rank 2, and so on — so the report's "rank-1 win rate" is meaningful
    only if you created the keys' agents with matching priorities.
    """
    agents: list[tuple[str, str, int]] = []
    for i, key in enumerate(keys):
        name = NAMES[i] if i < len(NAMES) else f"agent-{i + 1}"
        agents.append((name, key.strip(), i + 1))
    return agents


def bootstrap_user(base: str, n_agents: int) -> list[tuple[str, str, int]]:
    """Auto-provision a fresh user with N ranked agents (dev-mode only).

    This uses the magic-link `dev_token` shortcut, which only exists when
    the target API runs in dev mode. Against a hosted/production API,
    supply keys with --api-key / AGENTDRAFT_API_KEYS instead.

    Returns [(name, api_key, rank)] suitable for fire_one().
    """
    email = f"benchmark+{int(time.time())}@agentdraft.io"
    with httpx.Client(base_url=base, timeout=10.0) as web:
        r = web.post("/v1/auth/magic-link", json={"email": email})
        r.raise_for_status()
        body = r.json()
        if "dev_token" not in body:
            raise SystemExit(
                "This API did not return a dev token (it is not in dev mode), so the "
                "harness cannot auto-provision agents.\n"
                "Run against a hosted API by supplying agent keys instead:\n"
                "  1. Sign up at https://agentdraft.io (free Developer tier, no card)\n"
                "  2. Create agents with distinct priorities and copy their keys\n"
                "  3. Re-run with --api-key <key> (repeatable) or AGENTDRAFT_API_KEYS=k1,k2,..."
            )
        web.post("/v1/auth/verify", json={"token": body["dev_token"]}).raise_for_status()

        agents: list[tuple[str, str, int]] = []
        for i in range(n_agents):
            name = NAMES[i] if i < len(NAMES) else f"agent-{i + 1}"
            r = web.post(
                "/v1/dashboard/agents",
                json={
                    "name": name,
                    "scopes": ["availability:read", "bookings:write"],
                    "priority": i + 1,
                },
            )
            r.raise_for_status()
            agents.append((name, r.json()["plaintext_key"], i + 1))
    return agents


def resolve_agents(args: argparse.Namespace) -> list[tuple[str, str, int]]:
    """Pick the agent set: explicit keys if given, else dev-mode bootstrap."""
    keys = args.api_keys
    if not keys:
        env_keys = os.environ.get("AGENTDRAFT_API_KEYS", "").strip()
        if env_keys:
            keys = [k for k in env_keys.split(",") if k.strip()]
    if keys:
        return agents_from_keys(keys)
    return bootstrap_user(args.base_url, args.agents)


def run_round(agents: list[tuple[str, str, int]], slot_offset_hours: int, base: str) -> list[Result]:
    """Fire all agents at the same slot concurrently. Returns Result per agent."""
    start = (datetime.now(timezone.utc) + timedelta(hours=slot_offset_hours)).replace(
        minute=0, second=0, microsecond=0
    )
    end = start + timedelta(minutes=30)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(agents)) as pool:
        futures = [
            pool.submit(fire_one, name, key, rank, base, start, end, t0)
            for (name, key, rank) in agents
        ]
        return [f.result() for f in as_completed(futures)]


def aggregate(rounds: list[list[Result]]) -> dict:
    """Aggregate per-round results into report-shaped stats."""
    total_attempts = sum(len(r) for r in rounds)
    committed = sum(1 for r in rounds for x in r if x.status == "201")
    rejected = sum(1 for r in rounds for x in r if x.status == "409")
    errored = sum(1 for r in rounds for x in r if x.status == "error")

    # One commit per round is the contract: exactly one winner.
    rounds_with_exactly_one_winner = sum(
        1 for r in rounds if sum(1 for x in r if x.status == "201") == 1
    )
    rounds_with_double_commit = sum(
        1 for r in rounds if sum(1 for x in r if x.status == "201") > 1
    )
    rounds_with_no_winner = sum(
        1 for r in rounds if sum(1 for x in r if x.status == "201") == 0
    )
    accuracy = rounds_with_exactly_one_winner / len(rounds) if rounds else 0.0

    # Did the highest-priority agent (rank 1) win each round it raced?
    rank1_wins = 0
    rank1_races = 0
    for r in rounds:
        ranks_present = {x.agent_rank for x in r}
        if 1 in ranks_present:
            rank1_races += 1
            if any(x.agent_rank == 1 and x.status == "201" for x in r):
                rank1_wins += 1
    rank1_win_rate = rank1_wins / rank1_races if rank1_races else 0.0

    # Latency distribution across all attempts.
    latencies = sorted(x.elapsed_ms for r in rounds for x in r)
    p50 = median(latencies) if latencies else 0.0
    p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) >= 100 else (latencies[-1] if latencies else 0.0)

    return {
        "rounds": len(rounds),
        "agents_per_round": len(rounds[0]) if rounds else 0,
        "total_attempts": total_attempts,
        "committed": committed,
        "rejected_409": rejected,
        "errored": errored,
        "rounds_with_exactly_one_winner": rounds_with_exactly_one_winner,
        "rounds_with_double_commit": rounds_with_double_commit,
        "rounds_with_no_winner": rounds_with_no_winner,
        "conflict_resolution_accuracy": accuracy,
        "rank1_win_rate": rank1_win_rate,
        "latency_p50_ms": round(p50, 2),
        "latency_p99_ms": round(p99, 2),
    }


def render_markdown(report: dict, label: str, base: str) -> str:
    agg = report["aggregate"]
    started = report["started_at"]
    finished = report["finished_at"]
    lines = [
        f"# AgentDraft collision benchmark — {report['date']}",
        "",
        f"**Stack label:** `{label}`",
        f"**API base:** `{base}`",
        f"**Started:** {started}",
        f"**Finished:** {finished}",
        "",
        "## Headline numbers",
        "",
        f"- **Conflict resolution accuracy:** {agg['conflict_resolution_accuracy'] * 100:.2f}% "
        f"({agg['rounds_with_exactly_one_winner']} / {agg['rounds']} rounds had exactly one winner)",
        f"- **Rounds with double-commit:** {agg['rounds_with_double_commit']} (should be 0)",
        f"- **Rounds with no winner:** {agg['rounds_with_no_winner']} (should be 0)",
        f"- **Highest-priority-agent (rank 1) win rate:** {agg['rank1_win_rate'] * 100:.2f}%",
        f"- **Commits / 409s / errors:** {agg['committed']} / {agg['rejected_409']} / {agg['errored']}",
        f"- **Latency:** p50 = {agg['latency_p50_ms']} ms · p99 = {agg['latency_p99_ms']} ms",
        "",
        "## Method",
        "",
        f"Across {agg['rounds']} rounds, {agg['agents_per_round']} agents — each with a distinct "
        "ranked priority (1 = highest) — fired `POST /v1/bookings` concurrently at the same "
        "30-minute slot. Each round used a fresh future slot to ensure no cross-round leakage. "
        "Results were collected from the engine's response (`201 COMMITTED` or `409 OUTRANKED`).",
        "",
        "## Raw data",
        "",
        "See the accompanying `.json` file in the same directory.",
        "",
        "## Reproduce",
        "",
        "```bash",
        f"AGENTDRAFT_BASE_URL={base} AGENTDRAFT_API_KEYS=<key1,key2,...> \\",
        f"  python run.py --rounds {agg['rounds']} --label {label}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"AgentDraft collision benchmark · base={args.base_url}")
    print(f"  rounds={args.rounds}  label={args.label}")

    try:
        agents = resolve_agents(args)
    except httpx.HTTPError as e:
        print(f"  ✗ could not reach {args.base_url} — is the API running? ({e})", file=sys.stderr)
        return 1
    print(f"  ✓ using {len(agents)} ranked agents")

    started_at = datetime.now(timezone.utc).isoformat()
    rounds: list[list[Result]] = []

    # Each round targets a unique future slot so the engine doesn't carry
    # state between rounds. Slots step by 1 hour starting 24h ahead.
    for i in range(args.rounds):
        slot_offset = 24 + i
        try:
            results = run_round(agents, slot_offset, args.base_url)
        except httpx.HTTPError as e:
            print(f"  ✗ round {i} failed: {e}", file=sys.stderr)
            continue
        rounds.append(results)
        if (i + 1) % 10 == 0:
            print(f"  round {i + 1}/{args.rounds}")

    finished_at = datetime.now(timezone.utc).isoformat()
    agg = aggregate(rounds)

    report = {
        "schema_version": 1,
        "label": args.label,
        "base_url": args.base_url,
        "date": started_at[:10],
        "started_at": started_at,
        "finished_at": finished_at,
        "aggregate": agg,
        "rounds": [
            {
                "round": i,
                "results": [asdict(x) for x in r],
            }
            for i, r in enumerate(rounds)
        ],
    }

    stamp = started_at[:10]
    json_path = out_dir / f"benchmark-{stamp}.json"
    md_path = out_dir / f"benchmark-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    md_path.write_text(render_markdown(report, args.label, args.base_url))

    print()
    print(f"  ✓ wrote {json_path.relative_to(REPO_ROOT)}")
    print(f"  ✓ wrote {md_path.relative_to(REPO_ROOT)}")
    print()
    print(f"  accuracy={agg['conflict_resolution_accuracy'] * 100:.2f}% "
          f"rank1_win_rate={agg['rank1_win_rate'] * 100:.2f}% "
          f"p99={agg['latency_p99_ms']}ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
