# AgentDraft collision benchmark

A re-runnable measurement of [AgentDraft](https://agentdraft.io)'s conflict
engine under multi-agent contention. It fires N AI scheduling agents at the
**same calendar slot at the same instant** and records what the engine does.
This is the open harness behind the headline claim on agentdraft.io:

> **0 double-bookings across 500 concurrent agent attempts · 100% resolution
> accuracy · p99 commit 112 ms.**

Don't trust the number — re-run it yourself.

## At a glance

- **What it is:** a small, black-box load/correctness harness (one Python file).
- **Who it's for:** developers evaluating whether AgentDraft's race-safe booking
  actually holds under concurrency, and anyone who wants to reproduce the
  marketing benchmark independently.
- **How it works:** it only speaks HTTP through the public
  [`agentdraft`](https://pypi.org/project/agentdraft/) SDK. It imports **no**
  server internals, so it measures the running service as a real client would.
- **License:** MIT.

## What it measures

- **Conflict resolution accuracy** — fraction of rounds where *exactly one* agent
  commits (the engine's contract).
- **Highest-priority win rate** — fraction of rounds the rank-1 agent wins.
  Engine semantics say this should be 100%.
- **Latency** — p50 and p99 across all attempts.
- **Failure modes** — rounds with a double-commit, rounds with no winner, and
  outright errors. Each should be **0**.

## Run it against the hosted API (recommended)

```bash
pip install -r requirements.txt
```

1. Sign up at **https://agentdraft.io** — the free Developer tier needs no card.
2. Create a few agents with **distinct priorities** (1 = highest) and copy each
   agent's API key.
3. Run, passing the keys highest-priority first:

```bash
AGENTDRAFT_BASE_URL=https://api.agentdraft.io \
AGENTDRAFT_API_KEYS=avs_live_aaa,avs_live_bbb,avs_live_ccc \
  python run.py --rounds 100 --label agentdraft-prod
```

…or pass them as flags (first `--api-key` = highest priority):

```bash
python run.py --base-url https://api.agentdraft.io \
  --api-key avs_live_aaa --api-key avs_live_bbb --api-key avs_live_ccc \
  --rounds 100
```

> The free Developer tier caps bookings/month, so keep `--rounds` modest on a
> free account, or use a higher tier for a full 1000-round run.

## Run it against your own AgentDraft instance

If you operate an AgentDraft deployment in **dev mode**, the harness can
auto-provision the agents for you (no keys needed):

```bash
python run.py --base-url http://127.0.0.1:8080 --rounds 100 --agents 5
```

Auto-provisioning uses a dev-only sign-in shortcut; against a production API it
will tell you to supply `--api-key` instead.

## Output

Reports land in `./out/`:

- `benchmark-<UTC-date>.json` — full per-round results + aggregates.
- `benchmark-<UTC-date>.md` — human-readable report.

## CLI

```
--rounds   N      number of race rounds            (default 100)
--agents   N      agents per round when auto-provisioning (default 5)
--api-key  KEY    agent key; repeat per agent, first = highest priority
--base-url URL    AgentDraft API base URL          (env: AGENTDRAFT_BASE_URL)
--out-dir  DIR    output directory                 (default ./out)
--label    STR    label for the run                (default 'default-stack')
```

`AGENTDRAFT_API_KEYS` (comma-separated) is an alternative to repeated
`--api-key` flags.

## How this differs from a single-round demo

This runs many rounds silently, aggregates statistics, and writes files. The
underlying race — every agent fires `POST /v1/bookings` at one slot
concurrently — is identical each round; only the quantity and output shape
differ.

## Links

- AgentDraft: https://agentdraft.io
- Python SDK: https://pypi.org/project/agentdraft/
- Engine explainer: https://agentdraft.io/blog/race-engine

## Security

Found a problem? See [SECURITY.md](SECURITY.md). Never paste a live API key into
an issue.
