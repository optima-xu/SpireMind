"""Convert measured deck gaps and observed costs into a short, revisable goal."""

import math

from spiremind.core.run import RunIntent


def plan_run(state, analysis, feedback):
    needs = analysis.get("needs", {})
    priorities = sorted((key for key in needs if needs[key] > 0.6), key=lambda key: (-needs[key], key))[:3]
    evidence = [f"deck_gap:{key}={needs[key]:.3f}" for key in priorities]
    recent = [row for row in feedback if row.act == state.run.act and row.ended][-3:]
    if recent:
        evidence.append(f"observed_hp_loss_last_{len(recent)}_combats={sum(row.hp_lost for row in recent)}")
    reserve = math.ceil(state.run.max_hp * 0.25)
    if state.run.hp <= reserve:
        priorities = ["immediate_survival", *priorities[:2]]
        evidence.append(f"hp={state.run.hp}/{state.run.max_hp}")
    return RunIntent(
        act=state.run.act,
        observed_revision=state.revision,
        boss=state.run.boss,
        priorities=priorities,
        hp_reserve=reserve,
        release_potions=["verified_survival_need", "visible_boss_scaling_opportunity"],
        reconsider_when=["deck_or_resources_change", "new_boss_or_act", "combat_feedback"],
        evidence=evidence,
    )
