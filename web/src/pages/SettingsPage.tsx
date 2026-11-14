import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Cpu, KeyRound, Save, Stethoscope, Wifi, XCircle } from "lucide-react";
import { api } from "../api/client";
import { useI18n } from "../i18n";
import type {
  AppConfigPayload,
  BridgeProbeResult,
  LlmProbeResult,
  SessionStatus,
  SettingsPayload,
} from "../types";

interface SettingsPageProps {
  sessionStatus: SessionStatus;
}

export function SettingsPage({ sessionStatus }: SettingsPageProps) {
  const { t } = useI18n();
  const [payload, setPayload] = useState<SettingsPayload | null>(null);
  const [draft, setDraft] = useState<AppConfigPayload | null>(null);
  const [newApiKey, setNewApiKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [bridgeResult, setBridgeResult] = useState<BridgeProbeResult | null>(null);
  const [llmResult, setLlmResult] = useState<LlmProbeResult | null>(null);
  const [probingBridge, setProbingBridge] = useState(false);
  const [probingLlm, setProbingLlm] = useState(false);

  const isRunning = sessionStatus === "running" || sessionStatus === "stopping";

  const loadSettings = useCallback(async () => {
    try {
      const res = await api.getSettings();
      setPayload(res);
      setDraft(res.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  const applyPreset = (key: string) => {
    if (!payload || !draft) return;
    const preset = payload.presets[key];
    if (!preset) return;
    setDraft({
      ...draft,
      model: {
        ...draft.model,
        base_url: preset.base_url,
        model: preset.model,
        api_key_env: preset.api_key_env,
        json_mode: preset.json_mode,
        calculator_mode: preset.calculator_mode,
        temperature: preset.temperature,
        max_tokens: preset.max_tokens,
        extra_body: preset.extra_body ?? {},
      },
    });
    setSaveMsg(null);
  };

  const handleSave = async () => {
    if (!draft) return;
    setSaving(true);
    setSaveMsg(null);
    setError(null);
    try {
      const updated = await api.updateSettings({
        model: draft.model as unknown as Record<string, unknown>,
        game: draft.game as unknown as Record<string, unknown>,
        runtime: draft.runtime as unknown as Record<string, unknown>,
        strategy: draft.strategy as unknown as Record<string, unknown>,
        server: draft.server as unknown as Record<string, unknown>,
        new_api_key: newApiKey.trim() ? newApiKey.trim() : null,
      });
      setPayload(updated);
      setDraft(updated.config);
      setNewApiKey("");
      setSaveMsg(t("savedSuccess"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const runBridgeProbe = async () => {
    setProbingBridge(true);
    try {
      const res = await api.probeBridge(draft?.game.base_url);
      setBridgeResult(res);
    } catch (err) {
      setBridgeResult({
        ok: false,
        base_url: draft?.game.base_url ?? "",
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setProbingBridge(false);
    }
  };

  const runLlmProbe = async () => {
    setProbingLlm(true);
    try {
      const res = await api.probeLlm({
        model: draft?.model as unknown as Record<string, unknown>,
        new_api_key: newApiKey.trim() ? newApiKey.trim() : null,
      });
      setLlmResult(res);
    } catch (err) {
      setLlmResult({
        ok: false,
        configured_model: draft?.model.model ?? "",
        base_url: draft?.model.base_url ?? "",
        error: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setProbingLlm(false);
    }
  };

  if (!draft || !payload) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-8 text-center text-sm text-slate-400">
        {error || "..."}
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-12">
      {/* Left: Config Editor */}
      <div className="space-y-4 lg:col-span-8">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-bold text-slate-100">{t("settingsTitle")}</h2>
            <button
              type="button"
              disabled={saving || isRunning}
              onClick={() => void handleSave()}
              className="inline-flex items-center gap-1.5 rounded-xl bg-amber-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-45"
            >
              <Save className="h-3.5 w-3.5" />
              <span>{saving ? t("saving") : t("saveSettings")}</span>
            </button>
          </div>

          {isRunning && (
            <div className="mt-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-200">
              {t("confirmRunningDisabled")}
            </div>
          )}
          {saveMsg && (
            <div className="mt-3 rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-2.5 text-xs text-emerald-200">
              {saveMsg}
            </div>
          )}
          {error && (
            <div className="mt-3 rounded-xl border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs text-rose-200">
              {error}
            </div>
          )}

          {/* Presets */}
          <div className="mt-4">
            <div className="mb-2 text-xs font-medium text-slate-400">{t("presetsTitle")}</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(payload.presets).map(([key, preset]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => applyPreset(key)}
                  className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-amber-500/50 hover:text-amber-200"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>

          {/* Model Settings */}
          <div className="mt-5 border-t border-slate-800 pt-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-300">
              {t("modelSection")}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                label="Base URL"
                value={draft.model.base_url}
                onChange={(v) => setDraft({ ...draft, model: { ...draft.model, base_url: v } })}
              />
              <TextField
                label="Model"
                value={draft.model.model}
                onChange={(v) => setDraft({ ...draft, model: { ...draft.model, model: v } })}
              />
              <TextField
                label="API Key Env Var"
                value={draft.model.api_key_env}
                onChange={(v) => setDraft({ ...draft, model: { ...draft.model, api_key_env: v } })}
              />
              <label className="space-y-1 text-xs">
                <span className="block text-slate-400">Calculator Mode</span>
                <select
                  value={draft.model.calculator_mode}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      model: {
                        ...draft.model,
                        calculator_mode: e.target.value as "off" | "auto" | "required",
                      },
                    })
                  }
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-amber-500 focus:outline-none"
                >
                  <option value="off">off</option>
                  <option value="auto">auto</option>
                  <option value="required">required</option>
                </select>
              </label>

              <NumberField
                label="Temperature"
                step={0.1}
                value={draft.model.temperature ?? 0.1}
                onChange={(v) => setDraft({ ...draft, model: { ...draft.model, temperature: v } })}
              />
              <NumberField
                label="Max Tokens"
                step={100}
                value={draft.model.max_tokens ?? 1024}
                onChange={(v) =>
                  setDraft({ ...draft, model: { ...draft.model, max_tokens: Math.round(v) } })
                }
              />
            </div>

            <div className="mt-3 flex flex-wrap gap-4 text-xs">
              <label className="inline-flex items-center gap-2 text-slate-300">
                <input
                  type="checkbox"
                  checked={draft.model.json_mode}
                  onChange={(e) =>
                    setDraft({ ...draft, model: { ...draft.model, json_mode: e.target.checked } })
                  }
                  className="accent-amber-400"
                />
                <span>json_mode</span>
              </label>
              <label className="inline-flex items-center gap-2 text-slate-300">
                <input
                  type="checkbox"
                  checked={draft.strategy.combat_guards}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      strategy: { ...draft.strategy, combat_guards: e.target.checked },
                    })
                  }
                  className="accent-amber-400"
                />
                <span>strategy.combat_guards</span>
              </label>
              <label className="inline-flex items-center gap-2 text-slate-300">
                <input
                  type="checkbox"
                  checked={draft.runtime.allow_fallback}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      runtime: { ...draft.runtime, allow_fallback: e.target.checked },
                    })
                  }
                  className="accent-amber-400"
                />
                <span>runtime.allow_fallback</span>
              </label>
            </div>

            {/* API Key Box */}
            <div className="mt-4 rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="inline-flex items-center gap-1.5 font-medium text-slate-300">
                  <KeyRound className="h-3.5 w-3.5 text-amber-300" />
                  <span>
                    {t("apiKeyStatus")} ({payload.api_key.env_var})
                  </span>
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] ${
                    payload.api_key.configured
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-amber-500/15 text-amber-300"
                  }`}
                >
                  {payload.api_key.configured
                    ? `${t("configured")} (${payload.api_key.masked})`
                    : t("missing")}
                </span>
              </div>
              <label className="mt-2.5 block space-y-1 text-xs">
                <span className="block text-slate-400">{t("newApiKeyLabel")}</span>
                <input
                  type="password"
                  value={newApiKey}
                  onChange={(e) => setNewApiKey(e.target.value)}
                  placeholder={t("newApiKeyPlaceholder")}
                  className="w-full rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-amber-500 focus:outline-none"
                />
              </label>
            </div>
          </div>

          {/* Game & Runtime Settings */}
          <div className="mt-5 border-t border-slate-800 pt-4">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-300">
              {t("gameSection")} / {t("runtimeSection")}
            </h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <TextField
                label="Game Bridge URL"
                value={draft.game.base_url}
                onChange={(v) => setDraft({ ...draft, game: { ...draft.game, base_url: v } })}
              />
              <TextField
                label="Default Character"
                value={draft.game.character}
                onChange={(v) => setDraft({ ...draft, game: { ...draft.game, character: v } })}
              />
              <NumberField
                label="Default Ascension"
                step={1}
                value={draft.game.ascension}
                onChange={(v) =>
                  setDraft({ ...draft, game: { ...draft.game, ascension: Math.round(v) } })
                }
              />
              <NumberField
                label="Step Delay (s)"
                step={0.1}
                value={draft.runtime.step_delay_seconds}
                onChange={(v) =>
                  setDraft({ ...draft, runtime: { ...draft.runtime, step_delay_seconds: v } })
                }
              />
              <NumberField
                label="Max Steps"
                step={100}
                value={draft.runtime.max_steps}
                onChange={(v) =>
                  setDraft({ ...draft, runtime: { ...draft.runtime, max_steps: Math.round(v) } })
                }
              />
              <NumberField
                label="Max Context Tokens"
                step={1000}
                value={draft.runtime.max_context_tokens}
                onChange={(v) =>
                  setDraft({
                    ...draft,
                    runtime: { ...draft.runtime, max_context_tokens: Math.round(v) },
                  })
                }
              />
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-4 border-t border-slate-800 pt-3 font-mono text-[11px] text-slate-500">
            <span>
              {t("configPath")}: {payload.config_path}
            </span>
            <span>
              {t("envPath")}: {payload.env_path}
            </span>
          </div>
        </section>
      </div>

      {/* Right: Live Diagnostics (Doctor) */}
      <aside className="space-y-4 lg:col-span-4">
        <section className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Stethoscope className="h-4 w-4 text-sky-300" />
            <span>{t("doctorTitle")}</span>
          </h3>

          <div className="space-y-4">
            {/* Bridge Probe */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                  <Wifi className="h-3.5 w-3.5 text-amber-300" />
                  STS2AIMCP Bridge
                </span>
                <button
                  type="button"
                  disabled={probingBridge}
                  onClick={() => void runBridgeProbe()}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-200 hover:border-amber-500/50 disabled:opacity-50"
                >
                  {probingBridge ? t("testing") : t("testBridge")}
                </button>
              </div>
              {bridgeResult && (
                <div className="mt-2.5 space-y-1 border-t border-slate-800 pt-2 text-xs">
                  <div className="flex items-center gap-1.5">
                    {bridgeResult.ok ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <XCircle className="h-4 w-4 text-rose-400" />
                    )}
                    <span className={bridgeResult.ok ? "text-emerald-300" : "text-rose-300"}>
                      {bridgeResult.ok ? t("ok") : t("failed")}
                    </span>
                    {bridgeResult.latency_ms !== null && bridgeResult.latency_ms !== undefined && (
                      <span className="ml-auto font-mono text-slate-400">
                        {bridgeResult.latency_ms}ms
                      </span>
                    )}
                  </div>
                  {bridgeResult.observable && (
                    <div className="font-mono text-[11px] text-slate-300">
                      scene={bridgeResult.scene} · char={bridgeResult.character} · F
                      {bridgeResult.floor}
                    </div>
                  )}
                  {bridgeResult.error && (
                    <div className="break-all text-rose-300">{bridgeResult.error}</div>
                  )}
                </div>
              )}
            </div>

            {/* LLM Probe */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                  <Cpu className="h-3.5 w-3.5 text-sky-300" />
                  LLM Provider
                </span>
                <button
                  type="button"
                  disabled={probingLlm}
                  onClick={() => void runLlmProbe()}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs font-medium text-slate-200 hover:border-sky-500/50 disabled:opacity-50"
                >
                  {probingLlm ? t("testing") : t("testLlm")}
                </button>
              </div>
              {llmResult && (
                <div className="mt-2.5 space-y-1 border-t border-slate-800 pt-2 text-xs">
                  <div className="flex items-center gap-1.5">
                    {llmResult.ok ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <XCircle className="h-4 w-4 text-rose-400" />
                    )}
                    <span className={llmResult.ok ? "text-emerald-300" : "text-rose-300"}>
                      {llmResult.ok ? t("ok") : t("failed")}
                    </span>
                    {llmResult.latency_ms !== null && llmResult.latency_ms !== undefined && (
                      <span className="ml-auto font-mono text-slate-400">
                        {llmResult.latency_ms}ms
                      </span>
                    )}
                  </div>
                  {llmResult.response_model && (
                    <div className="font-mono text-[11px] text-slate-300">
                      model={llmResult.response_model}
                    </div>
                  )}
                  {llmResult.error && (
                    <div className="break-all text-rose-300">{llmResult.error}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>
      </aside>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <label className="space-y-1 text-xs">
      <span className="block text-slate-400">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-amber-500 focus:outline-none"
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step: number;
  onChange: (next: number) => void;
}) {
  return (
    <label className="space-y-1 text-xs">
      <span className="block text-slate-400">{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:border-amber-500 focus:outline-none"
      />
    </label>
  );
}
