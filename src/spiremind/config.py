import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelConfig(Settings):
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    timeout_seconds: float = Field(default=60, gt=0)
    max_tokens: int = Field(default=600, ge=128)
    max_completion_tokens: int | None = Field(default=None, ge=128)
    attempts: int = Field(default=3, ge=1, le=5)
    temperature: float | None = Field(default=0.2, ge=0, le=2)
    reasoning_effort: Literal["low", "medium", "high", "max"] | None = None
    json_mode: bool = True
    calculator_mode: Literal["required", "auto", "off"] = "required"
    require_exact_model: bool = False
    extra_body: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def reserved(self):
        reserved = {
            "model",
            "messages",
            "stream",
            "tools",
            "tool_choice",
            "max_tokens",
            "max_completion_tokens",
            "response_format",
        }
        if set(self.extra_body) & reserved:
            raise ValueError("extra_body cannot override provider-controlled request fields")
        return self


class GameConfig(Settings):
    base_url: str = "http://127.0.0.1:8080"
    character: str = "ironclad"
    ascension: int = Field(default=0, ge=0, le=20)
    transition_timeout: float = Field(default=90, gt=0)


class RuntimeConfig(Settings):
    runs_dir: Path = Path("runs")
    max_steps: int | None = Field(default=3000, ge=1)
    max_total_tokens: int | None = Field(default=None, ge=1)
    max_errors: int = Field(default=6, ge=1)  # Legacy configs; recovery now uses elapsed time.
    error_retry_seconds: float = Field(default=180, gt=0)
    max_seconds: float | None = Field(default=None, gt=0)
    context_tokens: int = Field(default=4000, ge=512)
    max_context_tokens: int = Field(default=16000, ge=1024)

    @field_validator("max_steps", "max_total_tokens", "max_seconds", mode="before")
    @classmethod
    def disabled_limit(cls, value):
        # TOML has no null; false explicitly disables a run limit, while zero is invalid.
        return None if value is False else value


class StrategyConfig(Settings):
    combat_guards: bool = True
    boss_potion_damage_fraction: float = Field(default=0.20, gt=0, le=1)


class MemoryConfig(Settings):
    enabled: bool = True
    reflection_use_model: bool = False
    reflection_requests: int = Field(default=4, ge=1, le=4)
    reflection_tokens: int = Field(default=12000, ge=1, le=12000)


class Config(Settings):
    model: ModelConfig = Field(default_factory=ModelConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    @classmethod
    def load(cls, path: Path | None = None):
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path else {}
        config = cls.model_validate(data)
        for env, field in (
            ("SPIREMIND_MODEL", "model"),
            ("SPIREMIND_BASE_URL", "base_url"),
            ("SPIREMIND_API_KEY_ENV", "api_key_env"),
        ):
            if os.getenv(env):
                setattr(config.model, field, os.environ[env])
        return config


def read_api_key(name: str) -> str:
    key = os.getenv(name)
    if not key and os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as registry:
                key = winreg.QueryValueEx(registry, name)[0]
        except OSError:
            pass
    if not key:
        raise ValueError(f"API key environment variable {name} is not set")
    return key
