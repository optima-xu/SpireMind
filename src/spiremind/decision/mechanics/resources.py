"""The resource transition shared by forecasts, search and verification."""


def spend_and_gain(hp, energy, max_hp, effects):
    """Pay costs before gains. Healing after HP depletion cannot rescue a play."""
    cost = effects.get("cost", 0)
    if not isinstance(cost, int) or cost < 0 or cost > energy:
        return None
    remaining_hp = hp - effects.get("hp_loss", 0)
    if remaining_hp <= 0:
        return None
    healed = remaining_hp + effects.get("heal", 0)
    return min(max_hp or healed, healed), energy - cost + effects.get("energy_gain", 0)
