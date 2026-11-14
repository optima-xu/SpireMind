"""Runtime configuration, `.env` loading, secret redaction, and Web UI settings persistence."""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, ConfigDict, Field

ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
_SECRET_KEY_PARTS = ("key", "token", "secret", "password", "authorization", "credential", "bearer")

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "json_mode": True,
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "json_mode": True,
        "extra_body": {},
    },
    "ollama": {
        "label": "Ollama (Local)",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:14b",
        "api_key_env": "OLLAMA_API_KEY",
        "json_mode": False,
        "extra_body": {},
    },
}


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class ModelConfig(Settings):
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-5.4-mini"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = Field(default=60.0, gt=0)
    attempts: int = Field(default=3, ge=1, le=5)
    backoff_seconds: float = Field(default=1.0, ge=0)
    retry_budget_seconds: float = Field(default=180.0, ge=0)
    temperature: float | None = Field(default=0.1, ge=0, le=2)
    max_tokens: int | None = Field(default=600, ge=128)
    max_completion_tokens: int | None = Field(default=None, ge=128)
    reasoning_effort: str | None = None
    json_mode: bool = False
    extra_body: dict[str, Any] = Field(default_factory=dict)
    calculator_mode: Literal["off", "auto", "required"] = "auto"
    calculator_max_rounds: int = Field(default=4, ge=1, le=8)
    require_exact_model: bool = False


class GameConfig(Settings):
    base_url: str = "http://127.0.0.1:8080"
    timeout_seconds: float = Field(default=10.0, gt=0)
    transition_timeout: float = Field(default=8.0, gt=0)
    character: str = "ironclad"
    ascension: int = Field(default=0, ge=0, le=20)
    retry_budget_seconds: float = Field(default=30.0, ge=0)


class RuntimeConfig(Settings):
    runs_dir: str | Path = "runs"
    step_delay_seconds: float = Field(default=0.2, ge=0)
    context_tokens: int = Field(default=4000, ge=256)
    max_context_tokens: int = Field(default=16000, ge=512)
    max_steps: int = Field(default=3000, ge=1)
    max_errors: int = Field(default=5, ge=1)
    error_retry_seconds: float = Field(default=180.0, ge=0)
    max_total_tokens: int | None = Field(default=None, gt=0)
    max_seconds: int | float | None = Field(default=None, gt=0)
    allow_fallback: bool = True
    verify_effects: bool = True


class StrategyConfig(Settings):
    combat_guards: bool = True
    boss_potion_damage_fraction: float = Field(default=0.20, ge=0.0, le=1.0)
    policy_version: str = "v2"


class ServerConfig(Settings):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)


class Config(BaseModel):
    """Top-level configuration; tolerates removed legacy sections such as `[memory]`."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    model: ModelConfig = Field(default_factory=ModelConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    @classmethod
    def load(cls, path: Path | None = None, *, env_path: Path | None = None) -> Config:
        return load_config(path, env_path=env_path)


def _strip_inline_comment(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] in {'"', "'"}:
        quote = raw[0]
        escaped = False
        chars: list[str] = []
        for idx, ch in enumerate(raw[1:], start=1):
            if escaped:
                chars.append(ch)
                escaped = False
                continue
            if ch == "\\" and quote == '"':
                escaped = True
                continue
            if ch == quote:
                rest = raw[idx + 1 :].strip()
                if rest and not rest.startswith("#"):
                    raise ValueError("trailing characters")
                return "".join(chars)
            chars.append(ch)
        raise ValueError("unclosed quote")
    comment_idx = raw.find(" #")
    if comment_idx != -1:
        return raw[:comment_idx].strip()
    if raw.startswith("#"):
        return ""
    return raw


def load_env_file(path: Path, *, override: bool = False) -> None:
    """Parse a literal `.env` file without evaluating expressions or overwriting process env."""
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig")
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ENV_LINE.match(raw_line)
        if not match:
            raise ValueError(f"Invalid .env syntax at line {line_no}")
        name, raw_val = match.groups()
        try:
            value = _strip_inline_comment(raw_val)
        except ValueError as exc:
            raise ValueError(f"Invalid .env value at line {line_no}: {exc}") from None
        if override or name not in os.environ:
            os.environ[name] = value


def _read_windows_registry_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value).strip()
    except OSError:
        return ""


def read_api_key(name: str, override: str | None = None) -> str:
    """Resolve an API key from explicit override, process environment, or Windows user env."""
    if override is not None and override.strip():
        return override.strip()
    env_val = os.getenv(name, "").strip()
    if env_val:
        return env_val
    return _read_windows_registry_env(name)


def mask_api_key(value: str | None) -> str | None:
    if not value:
        return None
    clean = value.strip()
    if not clean:
        return None
    if len(clean) >= 10:
        return f"{clean[:4]}****{clean[-4:]}"
    return "****"


def api_key_status(name: str) -> dict[str, Any]:
    val = read_api_key(name)
    return {
        "env_var": name,
        "configured": bool(val),
        "masked": mask_api_key(val),
    }


def safe_extra_body(value: Any) -> Any:
    """Recursively strip any secret-looking keys before serializing config or trace manifests."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            lowered = str(k).lower()
            if any(part in lowered for part in _SECRET_KEY_PARTS):
                continue
            result[str(k)] = safe_extra_body(v)
        return result
    if isinstance(value, list):
        return [safe_extra_body(item) for item in value]
    if isinstance(value, tuple):
        return [safe_extra_body(item) for item in value]
    return value


def redact_config(config: Config) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    data["model"]["extra_body"] = safe_extra_body(data["model"].get("extra_body", {}))
    return data


def canonical_bridge_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "http").lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    default_port = {"http": 80, "https": 443}.get(scheme)
    if port == default_port:
        netloc = host
    elif port is not None:
        netloc = f"{host}:{port}"
    else:
        netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if path.endswith("/mcp"):
        path = path[:-4]
    return urlunparse((scheme, netloc, path or "", "", "", ""))


def load_config(config_path: Path | None = None, *, env_path: Path | None = None) -> Config:
    """Load configuration from `.env`, TOML file (`config.local.toml` default), and env overrides."""
    load_env_file(env_path or Path(".env"), override=False)
    target = config_path or (Path("config.local.toml") if Path("config.local.toml").exists() else None)
    raw: dict[str, Any] = {}
    if target is not None and target.exists():
        raw = tomllib.loads(target.read_text(encoding="utf-8-sig"))
    cfg = Config.model_validate(raw)

    model_updates: dict[str, Any] = {}
    if env_model := os.getenv("SPIREMIND_MODEL", "").strip():
        model_updates["model"] = env_model
    if env_base := os.getenv("SPIREMIND_BASE_URL", "").strip():
        model_updates["base_url"] = env_base
    if model_updates:
        cfg = cfg.model_copy(update={"model": cfg.model.model_copy(update=model_updates)})

    if env_game := os.getenv("SPIREMIND_GAME_URL", "").strip():
        cfg = cfg.model_copy(update={"game": cfg.game.model_copy(update={"base_url": env_game})})

    return cfg


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Path):
        return json.dumps(str(value).replace("\\", "/"))
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(
            f"{json.dumps(str(k))} = {_toml_value(v)}" for k, v in value.items() if v is not None
        )
        return "{ " + items + " }"
    return json.dumps(value)


def _dump_toml_section(lines: list[str], header: str, data: dict[str, Any]) -> None:
    lines.append(f"[{header}]")
    nested: list[tuple[str, dict[str, Any]]] = []
    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, dict):
            if v:
                nested.append((f"{header}.{k}", v))
            continue
        lines.append(f"{k} = {_toml_value(v)}")
    lines.append("")
    for sub_header, sub_dict in nested:
        _dump_toml_section(lines, sub_header, sub_dict)


def render_config_toml(config: Config) -> str:
    raw = config.model_dump(mode="json")
    lines = ["# Generated by SpireMind configuration manager", ""]
    for section in ("model", "game", "runtime", "strategy", "server"):
        _dump_toml_section(lines, section, raw[section])
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


def save_settings(
    config: Config,
    config_path: Path,
    env_path: Path,
    new_api_key: str | None = None,
) -> None:
    """Persist validated settings to TOML and optionally update the configured `.env` API key."""
    _atomic_write(config_path, render_config_toml(config))

    if new_api_key is not None and new_api_key.strip():
        clean_key = new_api_key.strip()
        if "\n" in clean_key or "\r" in clean_key:
            raise ValueError("API key must not contain newlines")
        env_var = config.model.api_key_env
        existing_lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
        updated_lines: list[str] = []
        replaced = False
        for line in existing_lines:
            match = ENV_LINE.match(line)
            if match and match.group(1) == env_var:
                if not replaced:
                    updated_lines.append(f"{env_var}={clean_key}")
                    replaced = True
                continue
            updated_lines.append(line)
        if not replaced:
            updated_lines.append(f"{env_var}={clean_key}")
        _atomic_write(env_path, "\n".join(updated_lines).rstrip() + "\n")
        os.environ[env_var] = clean_key
