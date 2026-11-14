import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Backpack,
  Coins,
  Crown,
  Flame,
  FlaskConical,
  Heart,
  Layers,
  Map as MapIcon,
  Shield,
  Skull,
  Sparkles,
  Swords,
  X,
  Zap,
} from "lucide-react";
import { useI18n } from "../i18n";
import type { Action, Card, DecisionPayload, Enemy, GameState, Item, MapNode } from "../types";
import { GameText } from "../utils/gameText";

interface StateBoardProps {
  state: GameState | null;
  decision?: DecisionPayload | null;
  combatAssessment?: Record<string, unknown> | null;
}

const CARD_TYPE_STYLE: Record<string, string> = {
  attack: "border-rose-500/40 bg-rose-500/10 text-rose-200",
  skill: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  power: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  status: "border-slate-600 bg-slate-800/70 text-slate-300",
  curse: "border-violet-500/40 bg-violet-500/10 text-violet-200",
};

const NODE_TYPE_STYLE: Record<string, string> = {
  Monster: "border-slate-600 bg-slate-800 text-slate-200",
  Elite: "border-amber-500/50 bg-amber-500/15 text-amber-200",
  Boss: "border-rose-500/60 bg-rose-500/20 text-rose-200",
  RestSite: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
  Shop: "border-yellow-500/40 bg-yellow-500/15 text-yellow-200",
  Treasure: "border-cyan-500/40 bg-cyan-500/15 text-cyan-200",
  Unknown: "border-violet-500/40 bg-violet-500/15 text-violet-200",
};

function totalCardsInDeck(deck: Card[]): number {
  return deck.reduce((acc, card) => acc + (card.count || 1), 0);
}

export function StateBoard({ state, decision, combatAssessment }: StateBoardProps) {
  const { t } = useI18n();
  const [modalKind, setModalKind] = useState<"deck" | "relics" | null>(null);

  const assessmentMap = useMemo(() => {
    const byCardRef = new Map<string, Record<string, unknown>>();
    const evalRows = combatAssessment?.evaluated_actions;
    if (Array.isArray(evalRows)) {
      for (const row of evalRows) {
        if (row && typeof row === "object") {
          const rec = row as Record<string, unknown>;
          const cardId = typeof rec.card_id === "string" ? rec.card_id : null;
          if (cardId) byCardRef.set(cardId, rec);
        }
      }
    }
    return byCardRef;
  }, [combatAssessment]);

  const excludedReasons = useMemo(() => {
    const map = new Map<string, string>();
    if (decision?.excluded) {
      for (const [key, val] of Object.entries(decision.excluded)) {
        map.set(key, val);
      }
    }
    return map;
  }, [decision]);

  if (!state) {
    return (
      <div className="flex min-h-[420px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-8 text-center">
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-800/80 text-amber-300">
          <Swords className="h-6 w-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-200">{t("noStateTitle")}</h3>
        <p className="mt-1.5 max-w-md text-sm text-slate-400">{t("noStateHint")}</p>
      </div>
    );
  }

  const hpPct =
    state.run.max_hp > 0 ? Math.min(100, Math.max(0, (state.run.hp / state.run.max_hp) * 100)) : 0;
  const chosenActionId = decision?.action?.id ?? "";
  const chosenCardId = decision?.action?.card_id ?? "";
  const chosenNodeId = decision?.action?.node_id ?? "";

  const inCombat =
    Boolean(state.combat) && (state.scene === "combat" || state.scene === "card_selection");

  const deckTotal = totalCardsInDeck(state.run.deck);

  return (
    <div className="space-y-4">
      {/* Run Status Strip */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="rounded-lg bg-amber-500/15 px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-amber-300 ring-1 ring-amber-500/30">
              {state.run.character || "unknown"}
            </span>
            <span className="rounded-lg bg-slate-800 px-2 py-1 text-xs font-medium text-slate-300">
              A{state.run.ascension}
            </span>
            <span className="rounded-lg bg-sky-500/15 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-sky-300 ring-1 ring-sky-500/30">
              {state.scene}
            </span>
            <span className="text-xs text-slate-400">
              {t("actFloor")}:{" "}
              <strong className="text-slate-200">
                {state.run.act ?? "-"} / F{state.run.floor}
              </strong>
            </span>
            {state.run.boss && (
              <span className="inline-flex items-center gap-1 text-xs text-slate-400">
                <Crown className="h-3.5 w-3.5 text-rose-400" />
                <span>{state.run.boss}</span>
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setModalKind("deck")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-amber-500/50 hover:text-amber-200"
            >
              <Layers className="h-3.5 w-3.5 text-sky-300" />
              <span>
                {t("deck")} ({deckTotal})
              </span>
            </button>
            <button
              type="button"
              onClick={() => setModalKind("relics")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-amber-500/50 hover:text-amber-200"
            >
              <Backpack className="h-3.5 w-3.5 text-amber-300" />
              <span>
                {t("relics")} ({state.run.relics.length})
              </span>
            </button>
          </div>
        </div>

        {/* HP / Gold / Potions bar */}
        <div className="mt-3 grid gap-3 sm:grid-cols-12 sm:items-center">
          <div className="sm:col-span-4">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="inline-flex items-center gap-1 font-medium text-rose-300">
                <Heart className="h-3.5 w-3.5 fill-rose-500/30" />
                {t("hp")}
              </span>
              <span className="font-mono font-semibold text-slate-100">
                {state.run.hp} / {state.run.max_hp}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className={`h-full rounded-full transition-all ${
                  hpPct > 55 ? "bg-emerald-500" : hpPct > 28 ? "bg-amber-500" : "bg-rose-500"
                }`}
                style={{ width: `${hpPct}%` }}
              />
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm sm:col-span-2">
            <Coins className="h-4 w-4 text-amber-400" />
            <span className="font-mono font-semibold text-amber-200">{state.run.gold}</span>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 sm:col-span-6">
            <FlaskConical className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
            {state.run.potions.length === 0 ? (
              <span className="text-xs text-slate-500">{t("emptyPotions")}</span>
            ) : (
              state.run.potions.map((potion, idx) => (
                <span
                  key={`${potion.id}-${idx}`}
                  title={potion.text || potion.id}
                  className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-200"
                >
                  {potion.name || potion.id}
                </span>
              ))
            )}
          </div>
        </div>
      </section>

      {/* Combat Scene */}
      {inCombat && state.combat && (
        <section className="space-y-4">
          {/* Combat Metrics Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/75 px-4 py-3">
            <div className="flex flex-wrap items-center gap-4">
              <div className="flex items-center gap-1.5">
                <Zap className="h-4 w-4 text-amber-400" />
                <span className="text-xs text-slate-400">{t("energy")}</span>
                <span className="font-mono text-base font-bold text-amber-300">
                  {state.combat.energy}
                  {state.run.max_energy > 0 ? ` / ${state.run.max_energy}` : ""}
                </span>
              </div>

              <div className="flex items-center gap-1.5">
                <Shield className="h-4 w-4 text-sky-400" />
                <span className="text-xs text-slate-400">{t("block")}</span>
                <span className="font-mono text-base font-bold text-sky-300">
                  {state.combat.block}
                </span>
              </div>

              {state.combat.stars > 0 && (
                <div className="flex items-center gap-1.5">
                  <Sparkles className="h-4 w-4 text-cyan-300" />
                  <span className="text-xs text-slate-400">{t("stars")}</span>
                  <span className="font-mono text-sm font-bold text-cyan-200">
                    {state.combat.stars}
                  </span>
                </div>
              )}

              <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                {t("turn")} {state.combat.turn}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
              <span className="rounded bg-slate-800/90 px-2 py-0.5">
                {t("drawPile")}: <strong className="text-slate-200">{state.combat.draw.count}</strong>
              </span>
              <span className="rounded bg-slate-800/90 px-2 py-0.5">
                {t("discardPile")}:{" "}
                <strong className="text-slate-200">{state.combat.discard.count}</strong>
              </span>
              <span className="rounded bg-slate-800/90 px-2 py-0.5">
                {t("exhaustPile")}:{" "}
                <strong className="text-slate-200">{state.combat.exhaust.count}</strong>
              </span>
            </div>
          </div>

          {/* Deterministic Combat Assessment Quick Banner */}
          {combatAssessment && (
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/50 px-3.5 py-2 text-xs">
              {"incoming_attack_damage" in combatAssessment && (
                <span>
                  <span className="text-slate-400">{t("combatIncoming")}: </span>
                  <strong className="font-mono text-rose-300">
                    {String(combatAssessment.incoming_attack_damage)}
                  </strong>
                </span>
              )}
              {"unblocked_attack_damage" in combatAssessment && (
                <span>
                  <span className="text-slate-400">{t("combatUnblocked")}: </span>
                  <strong className="font-mono text-amber-300">
                    {String(combatAssessment.unblocked_attack_damage)}
                  </strong>
                </span>
              )}
              {"hp_after_intents_if_end_now" in combatAssessment && (
                <span>
                  <span className="text-slate-400">{t("combatMargin")}: </span>
                  <strong
                    className={`font-mono ${
                      Number(combatAssessment.hp_after_intents_if_end_now) > 0
                        ? "text-emerald-300"
                        : "text-rose-400"
                    }`}
                  >
                    {String(combatAssessment.hp_after_intents_if_end_now)}
                  </strong>
                </span>
              )}
              {typeof combatAssessment.survival_status === "string" && (
                <span className="ml-auto rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                  {t("survivalStatus")}: {combatAssessment.survival_status}
                </span>
              )}
            </div>
          )}

          {/* Player Powers */}
          {state.combat.powers.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {state.combat.powers.map((power, i) => (
                <span
                  key={`${power.id}-${i}`}
                  title={power.description || power.id}
                  className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 text-xs text-emerald-200"
                >
                  <span>{power.id}</span>
                  {power.amount !== null && power.amount !== undefined && (
                    <strong className="font-mono">{power.amount}</strong>
                  )}
                </span>
              ))}
            </div>
          )}

          {/* Enemies Grid */}
          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              {t("enemies")} ({state.combat.enemies.filter((e) => e.alive).length} /{" "}
              {state.combat.enemies.length})
            </h4>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {state.combat.enemies.map((enemy) => (
                <EnemyCard
                  key={enemy.ref}
                  enemy={enemy}
                  isTarget={decision?.action?.target_id === enemy.ref}
                  deadLabel={t("dead")}
                  intentsLabel={t("intents")}
                />
              ))}
            </div>
          </div>

          {/* Hand Cards */}
          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              {t("hand")} ({state.combat.hand.length})
            </h4>
            <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
              {state.combat.hand.map((card, idx) => {
                const evalRow = assessmentMap.get(card.ref);
                const selfLethal = Boolean(evalRow?.self_lethal);
                const excludedMsg =
                  excludedReasons.get(card.ref) || excludedReasons.get(card.id) || "";
                const isChosen =
                  Boolean(chosenCardId) && (card.ref === chosenCardId || card.id === chosenCardId);
                return (
                  <HandCardItem
                    key={`${card.ref || card.id}-${idx}`}
                    card={card}
                    isChosen={isChosen}
                    selfLethal={selfLethal}
                    excludedReason={excludedMsg}
                    unplayableLabel={t("unplayable")}
                    selfLethalLabel={t("selfLethalRisk")}
                    excludedLabel={t("excluded")}
                  />
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* Map Scene */}
      {state.map && state.scene === "map" && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h4 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <MapIcon className="h-4 w-4 text-amber-300" />
              <span>{t("mapSection")}</span>
            </h4>
            {state.map.current_node && (
              <span className="rounded-lg bg-slate-800 px-2.5 py-1 text-xs text-slate-300">
                {t("currentNode")}:{" "}
                <strong className="font-mono text-amber-300">{state.map.current_node}</strong>
              </span>
            )}
          </div>
          <div className="space-y-2">
            <div className="text-xs font-medium text-slate-400">{t("reachableNodes")}</div>
            <div className="flex flex-wrap gap-2">
              {state.map.nodes
                .filter((node) => node.reachable)
                .map((node) => (
                  <MapNodePill
                    key={node.id}
                    node={node}
                    selected={node.id === chosenNodeId}
                  />
                ))}
            </div>
          </div>
        </section>
      )}

      {/* Choices (Non-combat or card selection) */}
      {state.choices.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
          <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
            {t("choicesSection")} ({state.choices.length})
          </h4>
          <div className="grid gap-2.5 sm:grid-cols-2">
            {state.choices.map((choice, idx) => {
              const isChosen =
                (decision?.action?.option_id && decision.action.option_id === choice.id) ||
                (decision?.action?.card_id &&
                  choice.card &&
                  (decision.action.card_id === choice.card.ref ||
                    decision.action.card_id === choice.card.id));
              return (
                <div
                  key={`${choice.id}-${idx}`}
                  className={`rounded-xl border p-3 transition ${
                    isChosen
                      ? "border-emerald-400/70 bg-emerald-500/10 ring-1 ring-emerald-400/40"
                      : "border-slate-800 bg-slate-950/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-medium text-slate-100">
                      <GameText text={choice.label} />
                    </div>
                    {choice.price !== null && choice.price !== undefined && (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded bg-amber-500/15 px-1.5 py-0.5 font-mono text-xs text-amber-300">
                        <Coins className="h-3 w-3" />
                        {choice.price}
                      </span>
                    )}
                  </div>
                  {choice.description && (
                    <div className="mt-1 text-xs text-slate-300">
                      <GameText text={choice.description} />
                    </div>
                  )}
                  {choice.card && (
                    <div className="mt-2 rounded-lg border border-slate-800 bg-slate-900/80 p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-amber-200">
                          {choice.card.name || choice.card.id}
                          {choice.card.upgraded ? "+" : ""}
                        </span>
                        <span className="font-mono text-slate-400">
                          {choice.card.type} · {choice.card.cost ?? "-"}
                        </span>
                      </div>
                      {choice.card.text && (
                        <div className="mt-1 text-slate-300">
                          <GameText text={choice.card.text} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Legal Actions List */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
        <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
          {t("legalActionsSection")} ({state.legal_actions.length})
        </h4>
        <div className="flex flex-wrap gap-2">
          {state.legal_actions.map((action) => (
            <LegalActionPill
              key={action.id}
              action={action}
              selected={action.id === chosenActionId}
            />
          ))}
        </div>
      </section>

      {/* Deck / Relics Modal */}
      {modalKind && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          onClick={() => setModalKind(null)}
        >
          <div
            className="max-h-[82vh] w-full max-w-3xl overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3.5">
              <h3 className="text-sm font-semibold text-slate-100">
                {modalKind === "deck"
                  ? `${t("viewDeck")} (${deckTotal} ${t("cardsCount")})`
                  : `${t("viewRelics")} (${state.run.relics.length})`}
              </h3>
              <button
                type="button"
                onClick={() => setModalKind(null)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="max-h-[70vh] overflow-y-auto p-4">
              {modalKind === "deck" ? (
                <div className="grid gap-2 sm:grid-cols-2">
                  {state.run.deck.map((card, i) => (
                    <div
                      key={`${card.ref || card.id}-${i}`}
                      className="rounded-xl border border-slate-800 bg-slate-950/70 p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-slate-100">
                          {card.name || card.id}
                          {card.upgraded ? "+" : ""}
                          {card.count > 1 ? ` ×${card.count}` : ""}
                        </span>
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-amber-300">
                          {card.cost ?? "-"} · {card.type || "card"}
                        </span>
                      </div>
                      {card.text && (
                        <div className="mt-1.5 text-xs text-slate-300">
                          <GameText text={card.text} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {state.run.relics.map((relic: Item, i: number) => (
                    <div
                      key={`${relic.id}-${i}`}
                      className="rounded-xl border border-slate-800 bg-slate-950/70 p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold text-amber-200">
                          {relic.name || relic.id}
                        </span>
                        {relic.amount !== null && relic.amount !== undefined && (
                          <span className="rounded bg-amber-500/15 px-2 py-0.5 font-mono text-xs text-amber-300">
                            {relic.amount}
                          </span>
                        )}
                      </div>
                      {relic.text && (
                        <div className="mt-1 text-xs text-slate-300">
                          <GameText text={relic.text} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EnemyCard({
  enemy,
  isTarget,
  deadLabel,
  intentsLabel,
}: {
  enemy: Enemy;
  isTarget: boolean;
  deadLabel: string;
  intentsLabel: string;
}) {
  const hpPct = enemy.max_hp > 0 ? Math.min(100, Math.max(0, (enemy.hp / enemy.max_hp) * 100)) : 0;

  return (
    <div
      className={`rounded-xl border p-3.5 transition ${
        !enemy.alive
          ? "border-slate-800/60 bg-slate-950/40 opacity-50"
          : isTarget
            ? "border-amber-400/70 bg-amber-500/10 ring-1 ring-amber-400/40"
            : "border-slate-800 bg-slate-950/70"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-semibold text-slate-100">{enemy.name || enemy.id}</div>
          <div className="font-mono text-[11px] text-slate-500">{enemy.ref}</div>
        </div>
        {!enemy.alive ? (
          <span className="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[11px] text-slate-400">
            <Skull className="h-3 w-3" />
            {deadLabel}
          </span>
        ) : (
          enemy.block > 0 && (
            <span className="inline-flex items-center gap-1 rounded bg-sky-500/15 px-2 py-0.5 font-mono text-xs font-semibold text-sky-300">
              <Shield className="h-3 w-3" />
              {enemy.block}
            </span>
          )
        )}
      </div>

      <div className="mt-2.5">
        <div className="mb-1 flex justify-between text-xs font-mono">
          <span className="text-slate-400">HP</span>
          <span className="text-slate-200">
            {enemy.hp} / {enemy.max_hp}
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div className="h-full rounded-full bg-rose-500" style={{ width: `${hpPct}%` }} />
        </div>
      </div>

      {enemy.intents.length > 0 && enemy.alive && (
        <div className="mt-2.5 space-y-1">
          <div className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
            {intentsLabel}
          </div>
          {enemy.intents.map((intent, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between gap-2 rounded-lg bg-slate-900 px-2 py-1 text-xs"
            >
              <span className="inline-flex items-center gap-1 text-rose-300">
                <Flame className="h-3 w-3 shrink-0" />
                <span>{intent.type}</span>
              </span>
              <span className="font-mono font-semibold text-slate-200">
                {intent.damage !== null && intent.damage !== undefined
                  ? `${intent.damage}${intent.hits && intent.hits > 1 ? ` × ${intent.hits}` : ""}`
                  : intent.text || "-"}
              </span>
            </div>
          ))}
        </div>
      )}

      {enemy.powers.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {enemy.powers.map((power, idx) => (
            <span
              key={`${power.id}-${idx}`}
              title={power.description || power.id}
              className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-[11px] text-slate-300"
            >
              {power.id}
              {power.amount !== null && power.amount !== undefined ? ` ${power.amount}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function HandCardItem({
  card,
  isChosen,
  selfLethal,
  excludedReason,
  unplayableLabel,
  selfLethalLabel,
  excludedLabel,
}: {
  card: Card;
  isChosen: boolean;
  selfLethal: boolean;
  excludedReason: string;
  unplayableLabel: string;
  selfLethalLabel: string;
  excludedLabel: string;
}) {
  const typeKey = (card.type || "").toLowerCase();
  const typeBadge = CARD_TYPE_STYLE[typeKey] ?? "border-slate-700 bg-slate-800 text-slate-300";
  const unplayable = card.playable === false;

  return (
    <div
      className={`flex flex-col justify-between rounded-xl border p-3 transition ${
        isChosen
          ? "border-emerald-400/80 bg-emerald-500/10 ring-1 ring-emerald-400/40"
          : selfLethal
            ? "border-rose-500/50 bg-rose-950/25"
            : unplayable
              ? "border-slate-800/80 bg-slate-950/40 opacity-65"
              : "border-slate-800 bg-slate-950/75"
      }`}
    >
      <div>
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-semibold text-slate-100">
              {card.name || card.id}
              {card.upgraded ? <span className="ml-0.5 text-emerald-300">+</span> : null}
            </div>
            <div className="font-mono text-[10px] text-slate-500">{card.ref}</div>
          </div>
          <div className="flex items-center gap-1">
            {card.cost !== null && card.cost !== undefined && (
              <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-amber-500/20 px-1.5 font-mono text-xs font-bold text-amber-300 ring-1 ring-amber-500/40">
                {card.cost}
              </span>
            )}
            {card.star_cost !== null && card.star_cost !== undefined && card.star_cost > 0 && (
              <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-cyan-500/20 px-1.5 font-mono text-xs font-bold text-cyan-300 ring-1 ring-cyan-500/40">
                ★{card.star_cost}
              </span>
            )}
          </div>
        </div>

        <div className="mt-1.5 flex flex-wrap gap-1">
          {card.type && (
            <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${typeBadge}`}>
              {card.type}
            </span>
          )}
          {unplayable && (
            <span
              title={card.unplayable_reason || unplayableLabel}
              className="rounded border border-slate-700 bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400"
            >
              {card.unplayable_reason || unplayableLabel}
            </span>
          )}
          {selfLethal && (
            <span className="inline-flex items-center gap-1 rounded border border-rose-500/50 bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-rose-200">
              <AlertTriangle className="h-3 w-3" />
              {selfLethalLabel}
            </span>
          )}
          {excludedReason && (
            <span
              title={excludedReason}
              className="inline-flex items-center gap-1 rounded border border-amber-500/50 bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-200"
            >
              {excludedLabel}: {excludedReason}
            </span>
          )}
        </div>

        {card.text && (
          <div className="mt-2 text-xs leading-relaxed text-slate-300">
            <GameText text={card.text} />
          </div>
        )}
      </div>
    </div>
  );
}

function MapNodePill({ node, selected }: { node: MapNode; selected: boolean }) {
  const style = NODE_TYPE_STYLE[node.type] ?? "border-slate-700 bg-slate-800 text-slate-200";
  return (
    <div
      className={`rounded-xl border px-3 py-1.5 text-xs ${style} ${
        selected ? "ring-2 ring-emerald-400" : ""
      }`}
    >
      <span className="font-semibold">{node.type}</span>
      <span className="ml-1.5 font-mono text-[11px] opacity-80">({node.id})</span>
    </div>
  );
}

function LegalActionPill({ action, selected }: { action: Action; selected: boolean }) {
  return (
    <div
      title={action.description || action.id}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition ${
        selected
          ? "border-emerald-400/80 bg-emerald-500/15 font-semibold text-emerald-200 ring-1 ring-emerald-400/40"
          : "border-slate-800 bg-slate-950/70 text-slate-300"
      }`}
    >
      <span className="rounded bg-slate-800 px-1 py-0.5 font-mono text-[10px] text-slate-400">
        {action.kind}
      </span>
      <span>{action.label || action.id}</span>
    </div>
  );
}
