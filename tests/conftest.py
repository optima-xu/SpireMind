import pytest

from spiremind.environment.mcp import PROTOCOL
from spiremind.environment.mock import demo_states


@pytest.fixture
def states():
    return demo_states()


@pytest.fixture
def raw_decision():
    return {
        "decision_id": "run:f1:t1:1",
        "protocol_version": PROTOCOL,
        "state_version": 16,
        "decision_version": 7,
        "stable": True,
        "run_id": "fixture-run",
        "phase": "combat",
        "summary": {"turn": 1, "floor": 1, "character_id": "IRONCLAD", "ascension": 0},
        "context": {
            "run": {
                "character_id": "IRONCLAD",
                "current_hp": 65,
                "max_hp": 80,
                "gold": 99,
                "floor": 1,
                "deck": [{"card_id": "STRIKE", "name": "Strike"}],
                "boss_encounter": {"name": "Guardian"},
            },
            "combat": {
                "player_turn_phase": "Play",
                "player": {"current_hp": 65, "max_hp": 80, "energy": 3, "block": 0},
                "hand": [
                    {
                        "card_ref": "c0",
                        "card_id": "STRIKE",
                        "energy_cost": 1,
                        "rules_text": "Deal 6 damage.",
                        "dynamic_vars": {"Damage": {"preview_value": 6}},
                    }
                ],
                "enemies": [
                    {
                        "enemy_id": "SLIME",
                        "enemy_ref": "e0",
                        "current_hp": 10,
                        "intents": [{"intent_type": "Attack", "damage": 7, "hits": 2}],
                    }
                ],
                "end_turn_simulation": {"hidden_sentinel": "MUST_NOT_REACH_MODEL"},
                "piles": {"draw": {"count": 2, "order": "secret", "cards": ["secret_card"]}},
            },
            "run_analysis": {"sentinel": "EVALUATOR_EXCLUDED"},
        },
        "choices": [
            {
                "action_id": "combat:play:c0:e0",
                "kind": "play_card",
                "label": "Strike -> slime",
                "source": {"card_ref": "c0", "target_entity_ref": "e0"},
                "preview": {"lethal": True, "sentinel": "PREVIEW_EXCLUDED"},
                "risk_tags": [],
                "params_schema": {},
            },
            {
                "action_id": "combat:end_turn",
                "kind": "end_turn",
                "label": "End turn",
                "source": {},
                "risk_tags": ["incoming_damage"],
                "params_schema": {},
            },
        ],
        "knowledge": {"sentinel": "RAW_KNOWLEDGE_EXCLUDED"},
    }
