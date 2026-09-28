# Bridge contract and acceptance notes

The first adapter uses the direct HTTP v2 port of BMingSY/sts2-ai-mcp. See `bridge.lock.json` for the pinned revision. There is no generic stdio MCP client in v1.

## Read and execute boundary

- `GET /health`: require protocol `2026-07-18-v2-draft`, state >=16, decision >=7 and decision_v2 capability; reject incompatible. Upstream `untested` is recorded, not relabeled as upstream support.
- `GET /v2/decision/current` and `POST /v2/decision/wait`: `profile=ai_safe`, raw state/relevant game data disabled. Only stable snapshots enter normalization.
- Combat additionally requires `context.combat.player_turn_phase == "Play"`. The bridge can mark a snapshot stable during a turn's None phase when potion actions are present; the adapter waits for a changed decision without submitting end_turn.
- `POST /v2/decision/act`: exactly one current action ID plus decision ID, empty params. No retry of the mutation on timeout. A durable local pending journal precedes the request; reconcile against a changed stable decision before another mutation.
- `POST /v2/data/export`: read-only static data, exact game-version match. Description templates and their exported variables/costs are retained together. Exported base variants do not substitute for visible upgraded/live card text.

The policy receives canonical public fields. Raw payloads, `run_analysis`, action preview, consequence preview, hidden draw order, diagnostics and evaluator output are excluded. Audit files may contain full bridge observations and are gitignored.

State-change verification is not proof that an uncertain HTTP request actually executed. Runtime reports uncertain_actions separately; do not present those receipts as acknowledged game actions. The phase fix removes the observed None-phase requests rather than disguising their status.

## Observed contract limitations

`combat_selection` names both combat and noncombat card pickers. Route using the actual combat context/energy signal, not the phase name alone. Shop removal prices are nested in `card_removal`. Draw/discard/exhaust `stacks` are unordered and their per-card multiplicities must be preserved.

The v0.111.0 `simple_card_select` response gives selected_count but omits selected status on each card. Clicking an already selected card toggles it off. ProgressGuard infers selected references only from verified count deltas, prevents policy from canceling known selections, clears knowledge when the picker changes, and bounds repeated state/action pairs. It never alters the environment's legal action contract. After a restart with unknown selections it learns from subsequent verified deltas; it does not invent which card was selected.

The current upstream decision run context omits the act number; canonical act is null when unavailable, not a guessed number. This remains a state-coverage gap. Character-specific observations such as Osty require further adapter work and real Necrobinder validation. Standard Ironclad is the current real-game acceptance scope.

## Regression evidence

`tests/fixtures/v0.111.0-multiselect.json` is a reduced real Floor 12 response captured during local acceptance on 2026-09-27. It retains the eight-card multi-selection contract; run identity and unrelated state were removed. It is not a generated gameplay benchmark. `test_progress.py` verifies selection toggles, restart inference, invalidation, loop bounds and the captured response.

The local compatibility patch adapts renamed game API symbols. It does not validate multiplayer lobby capacity or room restart. Neither capability is used by the runtime.
