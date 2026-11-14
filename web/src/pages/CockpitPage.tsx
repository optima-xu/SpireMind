import { useState } from "react";
import {
  AlertTriangle,
  Eye,
  Pause,
  Play,
  PlugZap,
  RotateCcw,
  Square,
  StepForward,
} from "lucide-react";
import { api } from "../api/client";
import { DecisionPanel } from "../components/DecisionPanel";
import { StateBoard } from "../components/StateBoard";
import { useI18n } from "../i18n";
import type { PolicyMode, SessionSnapshot, StepRecord } from "../types";

interface CockpitPageProps {
  snapshot: SessionSnapshot;
  onSnapshotUpdate: (next: SessionSnapshot) => void;
  onRefreshSnapshot: () => Promise<void>;
}

const CHARACTERS = ["ironclad", "silent", "defect", "regent", "necrobinder"];

export function CockpitPage({
  snapshot,
  onSnapshotUpdate,
  onRefreshSnapshot,
}: CockpitPageProps) {
  const { t } = useI18n();
  const [character, setCharacter] = useState("ironclad");
  const [ascension, setAscension] = useState(0);
  const [policy, setPolicy] = useState<PolicyMode>(snapshot.policy || "model");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [selectedStep, setSelectedStep] = useState<StepRecord | null>(null);

  const isRunning = snapshot.status === "running";
  const isPaused = snapshot.status === "paused";
  const isActive = isRunning || isPaused || snapshot.status === "stopping";

  const runAction = async (label: string, fn: () => Promise<void>) => {
    setBusyAction(label);
    setActionError(null);
    try {
      await fn();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyAction(null);
    }
  };

  const inspectedState = selectedStep?.state ?? snapshot.state;
  const inspectedDecision = selectedStep?.decision ?? snapshot.latest_decision;
  const inspectedAssessment =
    selectedStep !== null
      ? selectedStep.combat_assessment ?? null
      : snapshot.combat_assessment;
  const inspectedContext =
    selectedStep !== null ? selectedStep.run_context ?? null : snapshot.run_context;

  return (
    <div className="space-y-4">
      {/* Control Toolbar */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="space-y-1 text-xs">
              <span className="block text-slate-400">{t("character")}</span>
              <select
                value={character}
                disabled={isActive}
                onChange={(e) => setCharacter(e.target.value)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100 focus:border-amber-500 focus:outline-none disabled:opacity-50"
              >
                {CHARACTERS.map((char) => (
                  <option key={char} value={char}>
                    {char}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1 text-xs">
              <span className="block text-slate-400">{t("ascension")}</span>
              <input
                type="number"
                min={0}
                max={20}
                disabled={isActive}
                value={ascension}
                onChange={(e) =>
                  setAscension(Math.min(20, Math.max(0, Number(e.target.value) || 0)))
                }
                className="w-20 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100 focus:border-amber-500 focus:outline-none disabled:opacity-50"
              />
            </label>

            <label className="space-y-1 text-xs">
              <span className="block text-slate-400">{t("policy")}</span>
              <select
                value={policy}
                disabled={isActive}
                onChange={(e) => setPolicy(e.target.value as PolicyMode)}
                className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100 focus:border-amber-500 focus:outline-none disabled:opacity-50"
              >
                <option value="model">{t("policyModel")}</option>
                <option value="rules">{t("policyRules")}</option>
              </select>
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={busyAction !== null || isActive}
              onClick={() =>
                void runAction("start", async () => {
                  setSelectedStep(null);
                  await api.startRun({ character, ascension, policy });
                  await onRefreshSnapshot();
                })
              }
              className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500 px-3.5 py-2 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Play className="h-3.5 w-3.5" />
              <span>{t("startNewRun")}</span>
            </button>

            <button
              type="button"
              disabled={busyAction !== null || isActive}
              onClick={() =>
                void runAction("attach", async () => {
                  setSelectedStep(null);
                  await api.attachRun({ policy });
                  await onRefreshSnapshot();
                })
              }
              className="inline-flex items-center gap-1.5 rounded-xl border border-sky-500/40 bg-sky-500/15 px-3.5 py-2 text-xs font-semibold text-sky-200 transition hover:bg-sky-500/25 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <PlugZap className="h-3.5 w-3.5" />
              <span>{t("attachRun")}</span>
            </button>

            <button
              type="button"
              disabled={busyAction !== null || isRunning}
              onClick={() =>
                void runAction("observe", async () => {
                  setSelectedStep(null);
                  const next = await api.observeBridge();
                  onSnapshotUpdate(next);
                })
              }
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-slate-600 hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Eye className="h-3.5 w-3.5" />
              <span>{t("observeBridge")}</span>
            </button>

            <button
              type="button"
              disabled={busyAction !== null || isRunning}
              onClick={() =>
                void runAction("step", async () => {
                  setSelectedStep(null);
                  const res = await api.stepOnce(policy);
                  onSnapshotUpdate(res.snapshot);
                })
              }
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/15 px-3 py-2 text-xs font-semibold text-emerald-200 transition hover:bg-emerald-500/25 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <StepForward className="h-3.5 w-3.5" />
              <span>{t("stepOnce")}</span>
            </button>

            {isPaused ? (
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  void runAction("resume", async () => {
                    await api.resumeRun();
                    await onRefreshSnapshot();
                  })
                }
                className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/20 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/30"
              >
                <Play className="h-3.5 w-3.5" />
                <span>{t("resume")}</span>
              </button>
            ) : (
              <button
                type="button"
                disabled={busyAction !== null || !isRunning}
                onClick={() =>
                  void runAction("pause", async () => {
                    await api.pauseRun();
                    await onRefreshSnapshot();
                  })
                }
                className="inline-flex items-center gap-1.5 rounded-xl border border-amber-500/40 bg-amber-500/15 px-3 py-2 text-xs font-semibold text-amber-200 hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-45"
              >
                <Pause className="h-3.5 w-3.5" />
                <span>{t("pause")}</span>
              </button>
            )}

            <button
              type="button"
              disabled={busyAction !== null || !isActive}
              onClick={() =>
                void runAction("stop", async () => {
                  await api.stopRun();
                  await onRefreshSnapshot();
                })
              }
              className="inline-flex items-center gap-1.5 rounded-xl border border-rose-500/40 bg-rose-500/15 px-3 py-2 text-xs font-semibold text-rose-200 hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Square className="h-3.5 w-3.5" />
              <span>{t("stop")}</span>
            </button>
          </div>
        </div>

        {/* Metrics Strip */}
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-slate-800/80 pt-2.5 text-xs text-slate-400">
          {snapshot.attempt_id && (
            <span>
              {t("attemptId")}:{" "}
              <strong className="font-mono text-slate-200">{snapshot.attempt_id}</strong>
            </span>
          )}
          <span>
            {t("steps")}:{" "}
            <strong className="font-mono text-slate-200">{snapshot.stats.steps}</strong>
          </span>
          <span>
            {t("verified")}:{" "}
            <strong className="font-mono text-emerald-300">
              {snapshot.stats.verified_actions}
            </strong>
          </span>
          <span>
            {t("rulesCount")}:{" "}
            <strong className="font-mono text-sky-300">{snapshot.stats.policy_rules}</strong>
          </span>
          <span>
            {t("fallbacks")}:{" "}
            <strong className="font-mono text-amber-300">{snapshot.stats.fallbacks}</strong>
          </span>
          <span>
            {t("tokens")}:{" "}
            <strong className="font-mono text-slate-200">
              {(snapshot.stats.input_tokens + snapshot.stats.output_tokens).toLocaleString()}
            </strong>
          </span>
        </div>
      </section>

      {/* Errors */}
      {(actionError || snapshot.last_error) && (
        <div className="flex items-start gap-2.5 rounded-2xl border border-rose-500/40 bg-rose-500/10 p-3.5 text-sm text-rose-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rose-400" />
          <div className="break-all">{actionError || snapshot.last_error}</div>
        </div>
      )}

      {/* Historical Inspection Banner */}
      {selectedStep && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs text-amber-200">
          <span>
            {t("inspectingStep")} #{selectedStep.step} ({selectedStep.scene})
          </span>
          <button
            type="button"
            onClick={() => setSelectedStep(null)}
            className="inline-flex items-center gap-1 rounded-lg bg-amber-500/20 px-2.5 py-1 font-semibold text-amber-100 hover:bg-amber-500/30"
          >
            <RotateCcw className="h-3 w-3" />
            <span>{t("backToLive")}</span>
          </button>
        </div>
      )}

      {/* Main 2-Column Cockpit */}
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <StateBoard
            state={inspectedState}
            decision={inspectedDecision}
            combatAssessment={inspectedAssessment}
          />
        </div>
        <div className="lg:col-span-5">
          <DecisionPanel
            decision={inspectedDecision}
            combatAssessment={inspectedAssessment}
            runContext={inspectedContext}
          />
        </div>
      </div>

      {/* Live Step Timeline */}
      {snapshot.recent_steps.length > 0 && (
        <section className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4">
          <h4 className="mb-2.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            {t("timeline")} ({snapshot.recent_steps.length})
          </h4>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {snapshot.recent_steps
              .slice()
              .reverse()
              .map((rec) => {
                const isSelected = selectedStep?.step === rec.step;
                const actionLabel =
                  rec.decision?.action?.label || rec.decision?.action?.kind || "-";
                return (
                  <button
                    key={rec.step}
                    type="button"
                    onClick={() => setSelectedStep(isSelected ? null : rec)}
                    className={`min-w-[165px] shrink-0 rounded-xl border p-2.5 text-left transition ${
                      isSelected
                        ? "border-amber-400 bg-amber-500/15"
                        : "border-slate-800 bg-slate-950/70 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 text-[11px]">
                      <span className="font-mono font-bold text-slate-200">#{rec.step}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                          rec.verify_ok === false
                            ? "bg-rose-500/20 text-rose-300"
                            : "bg-emerald-500/15 text-emerald-300"
                        }`}
                      >
                        {rec.latency_ms ?? 0}ms
                      </span>
                    </div>
                    <div className="mt-1 truncate text-xs font-medium text-slate-100">
                      {actionLabel}
                    </div>
                    <div className="mt-0.5 truncate font-mono text-[10px] text-slate-400">
                      {rec.scene}
                    </div>
                  </button>
                );
              })}
          </div>
        </section>
      )}
    </div>
  );
}
