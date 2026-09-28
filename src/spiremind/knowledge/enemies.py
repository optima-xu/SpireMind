from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from spiremind.core.state import Enemy
from spiremind.knowledge.library import version_matches


class EnemyMoveFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    name_zh: str = ""
    intent: str
    damage: dict[str, int | None] | None = None
    block: int | None = None
    heal: int | None = None
    powers: tuple[dict[str, str | int], ...] = ()


class EnemyFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    source_id: str
    name: str
    name_zh: str = ""
    type: str
    acts: tuple[str, ...] = ()
    hp: dict[str, int | None]
    moves: tuple[EnemyMoveFact, ...]
    pattern: dict[str, str] = Field(default_factory=dict)
    innate_powers: tuple[dict[str, str | int | None], ...] = ()
    traits: tuple[str, ...]
    strategy: tuple[str, ...]

    def context_view(self) -> dict:
        """Return only concise planning guidance, never the full local bestiary row."""
        traits = [trait for trait in self.traits if not trait.startswith("Encounter:")][:3]
        return {
            "id": self.id,
            "name": self.name,
            "name_zh": self.name_zh,
            "type": self.type,
            "traits": traits,
            "strategy": list(self.strategy[:2]),
        }


class EnemyCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    game_version: str
    source_version: str
    enemy_count: int
    source: dict
    enemies: tuple[EnemyFact, ...]

    @model_validator(mode="after")
    def validate_catalog(self):
        ids = [enemy.id for enemy in self.enemies]
        if self.enemy_count != len(self.enemies):
            raise ValueError("enemy_count does not match enemies")
        if len(ids) != len(set(ids)):
            raise ValueError("enemy ids must be unique")
        return self


class EnemyKnowledge:
    """Version-pinned local enemy facts selected by exact normalized bridge id."""

    DEFAULT_FILE = Path(__file__).parent / "enemies" / "v0.111.0.json"

    def __init__(self, path: Path | None = None):
        self.path = path or self.DEFAULT_FILE
        self.catalog = EnemyCatalog.model_validate_json(self.path.read_text(encoding="utf-8"))
        self._by_id = {enemy.id: enemy for enemy in self.catalog.enemies}

    def lookup(self, enemies: tuple[Enemy, ...], game_version: str) -> list[EnemyFact]:
        if not version_matches(self.catalog.game_version, game_version):
            return []
        result = []
        seen = set()
        for enemy in enemies:
            if not enemy.alive or enemy.id in seen:
                continue
            seen.add(enemy.id)
            fact = self._by_id.get(enemy.id)
            if fact:
                result.append(fact)
        return result

    def context_for(self, enemies: tuple[Enemy, ...], game_version: str) -> list[dict]:
        return [fact.context_view() for fact in self.lookup(enemies, game_version)]

    def get(self, enemy_id: str) -> EnemyFact | None:
        return self._by_id.get(enemy_id)

    def metadata(self) -> dict:
        return {
            "schema_version": self.catalog.schema_version,
            "game_version": self.catalog.game_version,
            "source_version": self.catalog.source_version,
            "enemy_count": self.catalog.enemy_count,
            "content_sha256": self.catalog.source.get("content_sha256", ""),
        }
