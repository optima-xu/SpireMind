"""FastAPI REST, settings redaction, session control, and WebSocket snapshot tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from spiremind.agent.session import AgentSession
from spiremind.config import Config, GameConfig
from spiremind.server.app import create_app
from tests.helpers import MockEnvironment, demo_states


@pytest.fixture
def api_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_TEST_SECRET_ENV", "sk-live-9876543210")
    cfg_path = tmp_path / "config.local.toml"
    env_path = tmp_path / ".env"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    cfg = Config.model_validate(
        {
            "model": {
                "model": "deepseek-chat",
                "api_key_env": "API_TEST_SECRET_ENV",
                "extra_body": {"thinking": {"type": "disabled"}},
            },
            "runtime": {"runs_dir": str(runs_dir), "step_delay_seconds": 0.01},
        }
    )

    env = MockEnvironment(demo_states())
    session = AgentSession(cfg, env_factory=lambda _c: env)
    app = create_app(
        cfg,
        config_path=cfg_path,
        env_path=env_path,
        session=session,
        web_dist_dir=tmp_path / "missing-dist",
    )
    return app, env, cfg_path, env_path


def test_health_and_settings_never_leak_plaintext_key(api_app) -> None:
    app, _env, cfg_path, env_path = api_app
    with TestClient(app) as client:
        h = client.get("/api/health")
        assert h.status_code == 200
        assert h.json()["ok"] is True

        s = client.get("/api/settings")
        assert s.status_code == 200
        payload = s.json()
        assert "sk-live-9876543210" not in s.text
        assert payload["api_key"] == {
            "env_var": "API_TEST_SECRET_ENV",
            "configured": True,
            "masked": "sk-l****3210",
        }
        assert "deepseek" in payload["presets"]

        put = client.put(
            "/api/settings",
            json={
                "game": {"character": "silent", "ascension": 4},
                "new_api_key": "sk-updated-00001111",
            },
        )
        assert put.status_code == 200
        assert "sk-updated-00001111" not in put.text
        assert put.json()["config"]["game"]["character"] == "silent"
        assert put.json()["api_key"]["masked"] == "sk-u****1111"
        assert "ascension = 4" in cfg_path.read_text(encoding="utf-8")
        assert "API_TEST_SECRET_ENV=sk-updated-00001111" in env_path.read_text(encoding="utf-8")


def test_session_observe_step_runs_and_websocket(api_app) -> None:
    app, env, _cfg_path, _env_path = api_app
    assert isinstance(app.state.ctx.config.game, GameConfig)

    with TestClient(app) as client:
        obs = client.get("/api/bridge/observe")
        assert obs.status_code == 200
        assert obs.json()["state"]["scene"] == "main_menu"

        step = client.post("/api/session/step", json={"policy": "rules"})
        assert step.status_code == 200
        assert step.json()["result"]["step"] == 1
        assert step.json()["snapshot"]["state"]["scene"] == "character_select"
        assert len(env.executed) == 1

        attempt_id = step.json()["snapshot"]["attempt_id"]
        runs = client.get("/api/runs")
        assert runs.status_code == 200
        assert runs.json()["runs"][0]["attempt_id"] == attempt_id

        detail = client.get(f"/api/runs/{attempt_id}")
        assert detail.status_code == 200
        assert len(detail.json()["steps"]) == 1

        with client.websocket_connect("/api/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "session_snapshot"
            assert msg["data"]["attempt_id"] == attempt_id
            ws.send_text("ping")
            pong = ws.receive_json()
            assert pong["type"] == "pong"
