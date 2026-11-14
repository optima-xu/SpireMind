import {
  AlertCircle,
  Bot,
  Calculator,
  ChevronDown,
  ChevronRight,
  Compass,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useState } from "react";
import { useI18n } from "../i18n";
import type { DecisionPayload } from "../types";

interface DecisionPanelProps {
  decision: DecisionPayload | null;
  combatAssessment?: Record<string, unknown> | null;
  runContext?: Record<string, unknown> | null;
}

export function DecisionPanel({
  decision,
  combatAssessment,
  runContext,
}: DecisionPanelProps) {
  const { t } = useI18n();
  const [showAssessment, setShowAssessment] = useState(false);

  const confidencePct =
    decision?.confidence !== undefined ? Math.round(decision.confidence * 100) : 0;

  return (
    <div className="space-y-4">
      {/* Main Decision Card */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Sparkles className="h-4 w-4 text-amber-300" />
            <span>{t("decisionTitle")}</span>
          </h3>
          {decision && <SourceBadge decision={decision} />}
        </div>

        {!decision ? (
          <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/50 p-6 text-center text-sm text-slate-400">
            {t("noDecisionHint")}
          </div>
        ) : (
          <div className="space-y-3.5">
            {/* Chosen Action */}
            <div className="rounded-xl border border-emerald-500/35 bg-emerald-500/10 p-3">
              <div className="text-[11px] font-medium uppercase tracking-wider text-emerald-300/80">
                {t("chosenAction")}
              </div>
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                <div className="text-base font-bold text-slate-50">
                  {decision.action.label || decision.action.kind}
                </div>
                <span className="rounded bg-slate-900/90 px-2 py-0.5 font-mono text-xs text-emerald-300">
                  {decision.action.kind}
                </span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5 font-mono text-[11px] text-slate-300">
                <span className="rounded bg-slate-900/70 px-1.5 py-0.5">
                  id: {decision.action.id}
                </span>
                {decision.action.card_id && (
                  <span className="rounded bg-slate-900/70 px-1.5 py-0.5">
                    card: {decision.action.card_id}
                  </span>
                )}
                {decision.action.target_id && (
                  <span className="rounded bg-slate-900/70 px-1.5 py-0.5">
                    target: {decision.action.target_id}
                  </span>
                )}
                {decision.action.node_id && (
                  <span className="rounded bg-slate-900/70 px-1.5 py-0.5">
                    node: {decision.action.node_id}
                  </span>
                )}
              </div>
            </div>

            {/* Confidence Bar */}
            <div>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-slate-400">{t("confidence")}</span>
                <span className="font-mono font-semibold text-slate-200">{confidencePct}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-amber-500 to-emerald-400"
                  style={{ width: `${Math.min(100, Math.max(0, confidencePct))}%` }}
                />
              </div>
            </div>

            {/* Reason */}
            {decision.reason && (
              <div>
                <div className="mb-1 text-xs font-medium text-slate-400">{t("reasoning")}</div>
                <p className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-sm leading-relaxed text-slate-200">
                  {decision.reason}
                </p>
              </div>
            )}

            {/* Calculations */}
            {decision.calculations && decision.calculations.length > 0 && (
              <div>
                <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-slate-400">
                  <Calculator className="h-3.5 w-3.5 text-sky-300" />
                  <span>{t("calculations")}</span>
                </div>
                <ul className="space-y-1 rounded-xl border border-slate-800 bg-slate-950/60 p-2.5 font-mono text-xs text-sky-200">
                  {decision.calculations.map((calc, i) => (
                    <li key={i} className="break-words">
                      • {calc}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Provider Error */}
            {decision.provider_error && (
              <div className="flex items-start gap-2 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-200">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
                <div>
                  <div className="font-semibold">{t("providerError")}</div>
                  <div className="mt-0.5 break-all opacity-90">{decision.provider_error}</div>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* RunContext Card */}
      {runContext && Object.keys(runContext).length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
          <h4 className="mb-2.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
            <Compass className="h-4 w-4 text-sky-300" />
            <span>{t("runContext")}</span>
          </h4>
          <RunContextView data={runContext} />
        </section>
      )}

      {/* Collapsible Combat Assessment */}
      {combatAssessment && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/75">
          <button
            type="button"
            onClick={() => setShowAssessment((v) => !v)}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-300 hover:bg-slate-800/40"
          >
            <span>{t("combatAssessment")}</span>
            {showAssessment ? (
              <ChevronDown className="h-4 w-4 text-slate-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-slate-400" />
            )}
          </button>
          {showAssessment && (
            <div className="border-t border-slate-800 p-3">
              <pre className="max-h-72 overflow-auto rounded-xl bg-slate-950 p-3 font-mono text-[11px] leading-relaxed text-slate-300">
                {JSON.stringify(combatAssessment, null, 2)}
              </pre>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function SourceBadge({ decision }: { decision: DecisionPayload }) {
  const { t } = useI18n();
  if (decision.fallback) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-rose-500/40 bg-rose-500/15 px-2.5 py-0.5 text-xs font-medium text-rose-200">
        {t("sourceFallback")}
      </span>
    );
  }
  if (decision.policy_rule) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-200">
        <ShieldCheck className="h-3.5 w-3.5" />
        <span>
          {t("sourceRule")}: {decision.policy_rule}
        </span>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-sky-500/40 bg-sky-500/15 px-2.5 py-0.5 text-xs font-medium text-sky-200">
      <Bot className="h-3.5 w-3.5" />
      <span>{decision.model_name || t("sourceModel")}</span>
    </span>
  );
}

function RunContextView({ data }: { data: Record<string, unknown> }) {
  const intent = data.intent as Record<string, unknown> | undefined;
  const archetypeScores = data.archetype_scores as Record<string, unknown> | undefined;
  const keyDecisions = Array.isArray(data.key_decisions) ? (data.key_decisions as string[]) : [];
  const bossPlan = typeof data.boss_plan === "string" ? data.boss_plan : "";
  const working = data.working as Record<string, unknown> | undefined;
  const currentGoal = working && typeof working.current_goal === "string" ? working.current_goal : "";

  return (
    <div className="space-y-2.5 text-xs">
      {currentGoal && (
        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2 text-amber-200">
          Goal: {currentGoal}
        </div>
      )}
      {intent && typeof intent.primary === "string" && intent.primary && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-amber-500/15 px-2 py-0.5 font-medium text-amber-200">
            {intent.primary}
          </span>
          {typeof intent.plan === "string" && intent.plan && (
            <span className="text-slate-300">{intent.plan}</span>
          )}
        </div>
      )}
      {bossPlan && <div className="text-slate-300">Boss Plan: {bossPlan}</div>}
      {archetypeScores && Object.keys(archetypeScores).length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {Object.entries(archetypeScores)
            .slice(0, 6)
            .map(([key, score]) => (
              <span
                key={key}
                className="rounded border border-slate-800 bg-slate-950/70 px-2 py-0.5 font-mono text-[11px] text-slate-300"
              >
                {key}: {typeof score === "number" ? score.toFixed(1) : String(score)}
              </span>
            ))}
        </div>
      )}
      {keyDecisions.length > 0 && (
        <ul className="space-y-1 border-t border-slate-800 pt-2 text-[11px] text-slate-400">
          {keyDecisions.slice(-5).map((item, i) => (
            <li key={i}>• {item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
