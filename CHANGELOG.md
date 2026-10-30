# Changelog

All notable changes to this project will be documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A shared decision frame, structured run intent, observed combat feedback and labeled offline `evaluate` cases.
- Durable application-level action recovery, idempotent transition commits and separate immediate-effect verification.
- Enforced module dependency checks and an offline installed-wheel smoke test.
- Current-phase diagnostics and calculator facts bound to legal actions, with validated numeric forecasts.
- Offline history bootstrap for interrupted traces, persistent holdout isolation and conditional tactical learning with counterexample retirement.
- Public live-state robustness regressions and three reproducible incremental benchmark reports.
- Explicit `--no-limits` and TOML `false` settings for disabling run step, time and cumulative-token limits.
- One-command Windows setup for Python, locked dependencies, configuration templates and the pinned game bridge.
- Main-menu-only `start`, cooperative `pause`/`resume`, process `status` and a Windows CLI launcher.
- Automatic literal `.env` and local TOML loading, preserving process environment values.
- English and Chinese READMEs with Quick Start and a concise technical report, plus a full command reference.

### Changed

- Separate core contracts, decision mechanics/policies, application orchestration, adapters, learning and evaluation; remove unused working-plan buffers and forwarding modules.
- Default model configuration uses `deepseek-flash` and `deepseek_api_key` on the DeepSeek endpoint, with thinking disabled explicitly.
- Scope background consolidation to affected evidence and revalidate retrieval against the complete current state.
- Resume reobserves the game and invalidates pre-pause choices; stopping preserves pending-action recovery.
- Retain legacy `run` and `step` commands for existing integrations.

### Fixed

- Publish in-memory strategy changes only after database commit; avoid repeated updates and run initialization during recovery.
- Reject known unpayable HP costs at the final execution boundary and isolate target-specific numeric previews.
- Read progress from the configured trace directory when control files live elsewhere.
- Reconcile retained receipts after post-action read failures before requesting another decision or sending a mutation.
- Track observe/execute/verify recovery separately, excluding healthy model latency from bridge deadlines.
- Recompute supported Body Slam damage after Block setup; include Plating at end turn without counting Pyre energy twice.
- Distinguish reported token usage from conservative safety estimates, including rejected HTTP requests.
- Retry transient Windows atomic-file replacement locks and roll back failed evidence imports together with cached partitions.

## [0.2.0] - 2026-10-02

### Added

- Agent-private working scopes, owned shared policies, version checks and structured handoffs.
- Evidence-backed episodes, FTS5/BM25 retrieval, offline/model reflection, promotion and contradiction audits.
- Reproducible offline/model benchmark CLI and deidentified training/holdout fixtures.
- Dedicated SQLite worker, bounded asynchronous trace pipeline and per-request budget accounting.
- Bounded arithmetic function tool with required Chat Completions tool-call round trips and per-decision calculation traces.
- Visible map path summaries and selected route horizons carried into shop decisions.

### Changed

- Reuse bounded combat assessments and parsed facts across guards, prompts and fallback.
- Cache exact-version card facts, deck profiles and experience retrieval with bounded LRU policies.
- Merge memory, snapshot and transition evidence in one rollback-safe transaction.
- Reuse calculator results for a single JSON repair; support jitter and Retry-After.
- Exercise installed wheel runtime and benchmark behavior in Windows/Linux CI.
- Account for the visible Plow stun threshold and Ringing card-play limit in bounded combat checks.
- Use persistent boss potions earlier when their effects can still pay back over multiple turns.
- Ground deck analysis and run decisions in exact-version card facts; reject unsupported named-card Strength plans.
- Avoid an extra elite on identical downstream routes at low HP, and inspect affordable offers at a critical last shop without requiring a purchase.
- Treat the v0.111.x Minion trait as non-damage-modifying when checking visible attack lethality.

### Fixed

- Settle flush requests queued during trace failure cleanup, including Python 3.11 scheduling.
- Exclude nested run archives from source distributions and anchor the public environment template.

## [0.1.0] - 2026-09-28

### Added

- Observable STS2 decision runtime with bound legal actions, verification, pending-action recovery and trace replay.
- OpenAI-compatible Chat Completions provider with exact-model checks and provider diagnostics.
- Working, run and skill memory with SQLite persistence and run isolation.
- Combat, run, map and event strategies plus deterministic fallback behavior.
- Versioned card knowledge and a local 115-entry STS2 v0.111.0 enemy reference.
- Bounded survival and attack-order search, including verified multi-card lethal plans.
- Pinned `sts2-ai-mcp` bridge build/install workflow for STS2 v0.111.0.
- Windows/Linux CI for Python 3.11 and 3.13.

### Security

- API keys remain in environment variables and are excluded from manifests and traces.
- Local configs, runs, saves, databases and bridge checkouts are excluded from source control.

[Unreleased]: https://github.com/optima-xu/SpireMind/compare/bfd7fb38da70f58079f2ce7e1893945fc6bff3d8...main
[0.2.0]: https://github.com/optima-xu/SpireMind/compare/v0.1.0...bfd7fb38da70f58079f2ce7e1893945fc6bff3d8
[0.1.0]: https://github.com/optima-xu/SpireMind/releases/tag/v0.1.0
