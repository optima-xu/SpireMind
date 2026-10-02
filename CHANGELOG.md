# Changelog

All notable changes to this project will be documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and releases use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Add a bounded arithmetic function tool with required Chat Completions tool-call round trips and per-decision calculation traces.
- Summarize visible map paths and carry the chosen route horizon into shop decisions.

### Changed

- Account for the visible Plow stun threshold and Ringing card-play limit in bounded combat checks.
- Use persistent boss potions earlier when their effects can still pay back over multiple turns.
- Ground deck analysis and run decisions in exact-version card facts; reject unsupported named-card Strength plans.
- Avoid an extra elite on identical downstream routes at low HP, and inspect affordable offers at a critical last shop without requiring a purchase.
- Treat the v0.111.x Minion trait as non-damage-modifying when checking visible attack lethality.

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

[Unreleased]: https://github.com/optima-xu/SpireMind/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/optima-xu/SpireMind/releases/tag/v0.1.0
