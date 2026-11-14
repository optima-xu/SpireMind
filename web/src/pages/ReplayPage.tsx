import { useCallback, useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw, Search } from "lucide-react";
import { api } from "../api/client";
import { DecisionPanel } from "../components/DecisionPanel";
import { StateBoard } from "../components/StateBoard";
import { useI18n } from "../i18n";
import type { RunDetailPayload, RunSummaryItem } from "../types";

export function ReplayPage() {
  const { t } = useI18n();
  const [runs, setRuns] = useState<RunSummaryItem[]>([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetailPayload | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [sceneFilter, setSceneFilter] = useState<string>("all");
  const [stepIdx, setStepIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    setLoadingRuns(true);
    setError(null);
    try {
      const res = await api.listRuns(100);
      setRuns(res.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const selectRun = useCallback(async (attemptId: string) => {
    setSelectedId(attemptId);
    setLoadingDetail(true);
    setError(null);
    setSceneFilter("all");
    setStepIdx(0);
    try {
      const payload = await api.getRun(attemptId);
      setDetail(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const filteredRuns = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return runs;
    return runs.filter(
      (r) =>
        r.attempt_id.toLowerCase().includes(q) ||
        (r.character ?? "").toLowerCase().includes(q) ||
        (r.outcome ?? "").toLowerCase().includes(q),
    );
  }, [runs, search]);

  const scenes = useMemo(() => {
    const set = new Set<string>();
    for (const s of detail?.steps ?? []) {
      if (s.scene) set.add(s.scene);
    }
    return Array.from(set);
  }, [detail]);

  const visibleSteps = useMemo(() => {
    const all = detail?.steps ?? [];
    if (sceneFilter === "all") return all;
    return all.filter((s) => s.scene === sceneFilter);
  }, [detail, sceneFilter]);

  useEffect(() => {
    if (stepIdx >= visibleSteps.length) {
      setStepIdx(Math.max(0, visibleSteps.length - 1));
    }
  }, [stepIdx, visibleSteps.length]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (event.key === "ArrowLeft") {
        setStepIdx((i) => Math.max(0, i - 1));
      } else if (event.key === "ArrowRight") {
        setStepIdx((i) => Math.min(Math.max(0, visibleSteps.length - 1), i + 1));
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [visibleSteps.length]);

  const currentStep = visibleSteps[stepIdx] ?? null;

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      {/* Left Run Browser */}
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/75 p-4 lg:col-span-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-100">{t("runsListTitle")}</h3>
          <button
            type="button"
            onClick={() => void loadRuns()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:border-amber-500/40 hover:text-amber-200"
          >
            <RefreshCw className={`h-3 w-3 ${loadingRuns ? "animate-spin" : ""}`} />
            <span>{t("refresh")}</span>
          </button>
        </div>

        <div className="relative mb-3">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("searchRuns")}
            className="w-full rounded-xl border border-slate-800 bg-slate-950 py-1.5 pr-3 pl-8 text-xs text-slate-100 placeholder:text-slate-500 focus:border-amber-500 focus:outline-none"
          />
        </div>

        <div className="max-h-[70vh] space-y-2 overflow-y-auto pr-1">
          {filteredRuns.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-500">{t("noRuns")}</div>
          ) : (
            filteredRuns.map((run) => {
              const selected = run.attempt_id === selectedId;
              return (
                <button
                  key={run.attempt_id}
                  type="button"
                  onClick={() => void selectRun(run.attempt_id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    selected
                      ? "border-amber-500/70 bg-amber-500/10"
                      : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs font-semibold text-slate-200">
                      {run.attempt_id}
                    </span>
                    <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                      {run.format === "steps_v2" ? t("formatV2") : t("formatLegacy")}
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                    <span className="uppercase text-amber-300">{run.character || "?"}</span>
                    {run.floor !== null && run.floor !== undefined && <span>F{run.floor}</span>}
                    <span>{run.steps_count} steps</span>
                    <span
                      className={`ml-auto rounded px-1.5 py-0.5 font-medium ${
                        run.outcome === "victory"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : run.outcome === "death"
                            ? "bg-rose-500/20 text-rose-300"
                            : "bg-slate-800 text-slate-300"
                      }`}
                    >
                      {run.outcome}
                    </span>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>

      {/* Right Step Replay Stage */}
      <div className="space-y-4 lg:col-span-9">
        {error && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
            {error}
          </div>
        )}

        {!detail ? (
          <div className="flex min-h-[420px] items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-8 text-sm text-slate-400">
            {loadingDetail ? "..." : t("selectRunHint")}
          </div>
        ) : (
          <>
            {/* Scrubber Header */}
            <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="font-mono text-sm font-bold text-slate-100">
                    {detail.attempt_id}
                  </div>
                  <div className="mt-0.5 text-xs text-slate-400">
                    {detail.meta.character || "?"} · {detail.steps.length} steps ·{" "}
                    {t("hotkeyHint")}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={stepIdx <= 0}
                    onClick={() => setStepIdx((i) => Math.max(0, i - 1))}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                    <span>{t("prevStep")}</span>
                  </button>
                  <span className="min-w-[78px] text-center font-mono text-xs text-slate-300">
                    {visibleSteps.length > 0 ? stepIdx + 1 : 0} / {visibleSteps.length}
                  </span>
                  <button
                    type="button"
                    disabled={stepIdx >= visibleSteps.length - 1}
                    onClick={() =>
                      setStepIdx((i) => Math.min(Math.max(0, visibleSteps.length - 1), i + 1))
                    }
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-40"
                  >
                    <span>{t("nextStep")}</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>

              {visibleSteps.length > 1 && (
                <input
                  type="range"
                  min={0}
                  max={visibleSteps.length - 1}
                  value={stepIdx}
                  onChange={(e) => setStepIdx(Number(e.target.value))}
                  className="mt-3 w-full accent-amber-400"
                />
              )}

              {/* Scene Filters */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setSceneFilter("all");
                    setStepIdx(0);
                  }}
                  className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                    sceneFilter === "all"
                      ? "bg-amber-500/20 text-amber-200 ring-1 ring-amber-500/40"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t("allScenes")}
                </button>
                {scenes.map((scene) => (
                  <button
                    key={scene}
                    type="button"
                    onClick={() => {
                      setSceneFilter(scene);
                      setStepIdx(0);
                    }}
                    className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                      sceneFilter === scene
                        ? "bg-sky-500/20 text-sky-200 ring-1 ring-sky-500/40"
                        : "bg-slate-800 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {scene}
                  </button>
                ))}
              </div>
            </section>

            {/* Replay Dual Panes */}
            {currentStep && (
              <div className="grid gap-4 xl:grid-cols-12">
                <div className="xl:col-span-7">
                  <StateBoard
                    state={currentStep.state ?? null}
                    decision={currentStep.decision ?? null}
                    combatAssessment={currentStep.combat_assessment ?? null}
                  />
                </div>
                <div className="xl:col-span-5">
                  <DecisionPanel
                    decision={currentStep.decision ?? null}
                    combatAssessment={currentStep.combat_assessment ?? null}
                    runContext={currentStep.run_context ?? null}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
