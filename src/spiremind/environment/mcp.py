"""Direct HTTP transport to the STS2 MCP bridge's AI-safe v2 port."""

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

from spiremind.config import GameConfig
from spiremind.core.actions import Action, ActionResult
from spiremind.core.state import GameState, PublicFacts
from spiremind.knowledge.cards import CardFact
from spiremind.runtime.validator import ActionValidator
from spiremind.runtime.verifier import verify_transition

from .base import EnvironmentError, StaleDecision, TransitionPending
from .normalize import norm_id, normalize

PROTOCOL = "2026-07-18-v2-draft"


class MCPEnvironment:
    def __init__(self, config: GameConfig, journal: Path, client: httpx.AsyncClient | None = None):
        self.config = config
        self.client = client or httpx.AsyncClient(base_url=config.base_url, timeout=35, trust_env=False)
        self.journal = journal
        self.state: GameState | None = None
        self.game_version = "unknown"
        self.revision = 0
        self.lock = asyncio.Lock()
        self.pending = self._load_pending()
        self.cached_decision: dict | None = None
        self.raw_sink = None

    def _load_pending(self) -> dict | None:
        if not self.journal.exists():
            return None
        try:
            value = json.loads(self.journal.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("pending journal is not an object")
            if not all(
                isinstance(value.get(key), str) and value[key] for key in ("decision_id", "action_id")
            ):
                raise ValueError("pending journal has no action identity")
            phase = value.get("phase", "dispatched")
            if phase not in {"prepared", "dispatched"}:
                raise ValueError("pending journal has an invalid phase")
            return value | {"phase": phase}
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            # A broken diagnostic file must not brick every future launch. Preserve it for inspection.
            corrupt = self.journal.with_name(self.journal.name + ".corrupt")
            try:
                corrupt.unlink(missing_ok=True)
                self.journal.replace(corrupt)
            except OSError:
                self.journal.unlink(missing_ok=True)
            return None

    async def card_facts(self) -> list[CardFact]:
        """Read versioned static ModelDb facts; never use preview/evaluator endpoints."""
        data = await self._request("POST", "/v2/data/export", json={})
        metadata = data.get("metadata") or {}
        version = metadata.get("game_version")
        if not version or version == "unknown" or version != self.game_version:
            raise EnvironmentError("Card export version does not match the running game")
        result = []
        for identity, item in (data.get("collections") or {}).get("cards", {}).items():
            if not isinstance(item, dict):
                continue
            text = item.get("description") or item.get("rules_text")
            if text:
                result.append(
                    CardFact(
                        card_id=norm_id(identity),
                        game_version=version,
                        source_version=f"loaded_game_model:{version}:mod-{metadata.get('mod_version')}",
                        text=text,
                        upgraded=bool(item.get("upgraded", False)),
                        cost=item.get("cost"),
                        star_cost=item.get("star_cost"),
                        type=item.get("type", "").lower(),
                        values=PublicFacts.of(item.get("vars") or {}),
                    )
                )
        if not result:
            raise EnvironmentError("Bridge exported no usable card facts")
        return result

    async def health(self) -> dict:
        data = await self._request("GET", "/health")
        protocol = data.get("protocol_version") or data.get("v2_protocol_version")
        if (
            protocol != PROTOCOL
            or data.get("state_version", 0) < 16
            or data.get("decision_version", 0) < 7
            or (data.get("capabilities") or {}).get("decision_v2") is not True
            or (data.get("compatibility") or {}).get("status") == "incompatible"
        ):
            raise EnvironmentError("Bridge contract is incompatible (requires v2/state16/decision7)")
        self.game_version = data.get("game_version") or "unknown"
        return data

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        response = await self.client.request(method, path, **kwargs)
        try:
            body = response.json()
        except ValueError:
            raise EnvironmentError(f"Bridge returned non-JSON HTTP {response.status_code}") from None
        if not response.is_success or body.get("ok") is False:
            code = (body.get("error") or {}).get("code", f"http_{response.status_code}")
            if code in {"stale_decision", "invalid_action", "invalid_target", "action_not_allowed"}:
                raise StaleDecision(code)
            if code in {"state_unstable", "decision_unavailable", "state_unavailable"}:
                raise TransitionPending(code)
            raise EnvironmentError(f"Bridge error: {code}")
        return body.get("data", body)

    def _normalize(self, value: dict) -> GameState:
        if not self._ready(value):
            raise TransitionPending("Combat has not entered the Play phase")
        if value.get("protocol_version") != PROTOCOL:
            raise EnvironmentError("Unexpected decision protocol")
        if self.state is None or value["decision_id"] != self.state.decision_id:
            self.revision += 1
        if self.raw_sink:
            self.raw_sink(value)
        self.state = normalize(value, self.revision, self.game_version)
        return self.state

    @staticmethod
    def _ready(value: dict) -> bool:
        if not value.get("stable"):
            return False
        if value.get("phase") == "combat":
            combat = (value.get("context") or {}).get("combat") or {}
            return combat.get("player_turn_phase") == "Play"
        return True

    def _write_pending(self) -> None:
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.journal.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as out:
            json.dump(self.pending, out)
            out.flush()
            os.fsync(out.fileno())
        # Windows can briefly deny replacement while another process holds the file.
        # Retry only persistence; execute() must not dispatch until this succeeds.
        for attempt in range(6):
            try:
                temporary.replace(self.journal)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(min(0.05 * 2**attempt, 0.4))

    def _save_pending(self, action: Action) -> None:
        self.pending = {
            "decision_id": action.decision_id,
            "action_id": action.id,
            "phase": "prepared",
        }
        self._write_pending()

    def _mark_dispatched(self) -> None:
        if self.pending:
            self.pending["phase"] = "dispatched"
            self._write_pending()

    def _clear_pending(self) -> None:
        self.journal.unlink(missing_ok=True)
        self.pending = None

    async def _wait(self, after: str | None = None) -> dict:
        deadline = time.monotonic() + self.config.transition_timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            try:
                async with asyncio.timeout(remaining):
                    data = await self._request(
                        "POST",
                        "/v2/decision/wait",
                        json={
                            "timeout_ms": max(1, min(10000, int(remaining * 1000))),
                            "profile": "ai_safe",
                            "include_raw_state": False,
                            "include_relevant_game_data": False,
                            "after_decision_id": after,
                        },
                    )
                d = data.get("decision")
                if data.get("available") and d and d["decision_id"] != after:
                    if self._ready(d):
                        return d
                    if self.raw_sink:
                        self.raw_sink(d)
                    after = d["decision_id"]
            except (TimeoutError, TransitionPending, httpx.TransportError):
                pass
            remaining = deadline - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(min(0.3, remaining))
        raise TransitionPending("No new stable decision before deadline; pending action retained")

    async def _reconcile_pending(self) -> GameState:
        """Resolve a durable action without ever resending its mutation.

        The v2 bridge leases an accepted decision ID and stops exposing it as stable current.
        Therefore a still-visible old decision proves that a prepared/dispatched request was not
        accepted; an unavailable or changed decision must instead be reconciled by waiting.
        """
        assert self.pending is not None
        previous = self.pending["decision_id"]
        try:
            data = await self._request(
                "GET",
                "/v2/decision/current",
                params={
                    "profile": "ai_safe",
                    "include_raw_state": "false",
                    "include_relevant_game_data": "false",
                },
            )
        except TransitionPending:
            data = {}
        value = data.get("decision") if data.get("available") else None
        if value and self._ready(value):
            state = self._normalize(value)
            self._clear_pending()
            return state
        value = await self._wait(previous)
        state = self._normalize(value)
        self._clear_pending()
        return state

    async def observe(self) -> GameState:
        if self.cached_decision is not None:
            value, self.cached_decision = self.cached_decision, None
            state = self._normalize(value)
            self._clear_pending()
            return state
        if self.pending:
            return await self._reconcile_pending()
        try:
            data = await self._request(
                "GET",
                "/v2/decision/current",
                params={
                    "profile": "ai_safe",
                    "include_raw_state": "false",
                    "include_relevant_game_data": "false",
                },
            )
        except TransitionPending:
            data = {}
        value = data.get("decision") if data.get("available") else None
        if value and not self._ready(value):
            if self.raw_sink:
                self.raw_sink(value)
            value = await self._wait(value["decision_id"])
        return self._normalize(value or await self._wait())

    async def legal_actions(self) -> list[Action]:
        return list((await self.observe()).legal_actions)

    async def execute(self, action: Action) -> ActionResult:
        async with self.lock:
            if self.pending:
                raise TransitionPending("Resolve the previous action before executing another")
            if self.state is None:
                raise EnvironmentError("Observe before executing")
            ActionValidator().validate(self.state, action)
            self._save_pending(action)  # durable BEFORE the single, non-retried mutation
            self._mark_dispatched()
            try:
                data = await self._request(
                    "POST",
                    "/v2/decision/act",
                    json={
                        "decision_id": action.decision_id,
                        "action_id": action.id,
                        "params": {},
                        "client_note": "SpireMind v1",
                    },
                )
            except StaleDecision:
                self._clear_pending()  # explicit rejection: no mutation accepted
                raise
            except (httpx.TransportError, EnvironmentError):
                return ActionResult(
                    status="uncertain", action_id=action.id, previous_decision_id=action.decision_id
                )
            status = data.get("status", "uncertain")
            if status in {"failed", "rejected"}:
                # Do not assume failure implies no side effects. Reconcile before continuing.
                return ActionResult(
                    status=status,
                    action_id=action.id,
                    previous_decision_id=action.decision_id,
                    error="bridge_action_failed",
                )
            next_decision = data.get("next_decision")
            if isinstance(next_decision, dict):
                self.cached_decision = next_decision
            return ActionResult(
                status=status,
                action_id=action.id,
                previous_decision_id=action.decision_id,
                next_decision_id=(next_decision or {}).get("decision_id"),
            )

    async def verify(self, before: GameState, action: Action, after: GameState) -> bool:
        return verify_transition(before, action, after)

    async def close(self):
        await self.client.aclose()
