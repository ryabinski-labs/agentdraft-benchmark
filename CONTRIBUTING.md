# Contributing

Thanks for your interest in the AgentDraft collision benchmark.

This repo is a small, self-contained measurement tool. The most valuable
contributions are:

- **Reproductions** — run the benchmark against the hosted API or your own
  AgentDraft instance and share the generated report (`out/benchmark-*.md`) in
  an issue, especially if the numbers diverge from what agentdraft.io claims.
- **Harness improvements** — clearer output, additional metrics, more agent
  stacks to label and compare.

## Development

```bash
pip install -r requirements.txt pytest
python -m py_compile run.py
python -m pytest -q          # offline smoke tests, no network needed
```

## Pull requests

- Keep changes focused and the harness a black-box HTTP client — it must not
  import AgentDraft server internals.
- CI (compile + smoke tests) must pass. A maintainer merges once checks are green.
- Never include a live API key (`avs_live_…`) in code, tests, issues, or PRs.

See [MAINTAINERS.md](MAINTAINERS.md) for who can merge, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for community expectations.
