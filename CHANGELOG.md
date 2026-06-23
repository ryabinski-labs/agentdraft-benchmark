# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Initial public release of the AgentDraft collision benchmark harness,
  extracted from the AgentDraft monorepo.
- `--api-key` / `AGENTDRAFT_API_KEYS` mode so the benchmark runs against the
  hosted API (`https://api.agentdraft.io`) with your own free agent keys,
  without the dev-only magic-link bootstrap.
- Offline smoke tests and fork-safe CI.
