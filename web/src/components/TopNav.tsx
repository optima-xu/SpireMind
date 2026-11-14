import { Activity, History, Languages, Settings, Swords, Wifi, WifiOff } from "lucide-react";
import { useI18n } from "../i18n";
import type { SessionStatus, TabId } from "../types";

interface TopNavProps {
  activeTab: TabId;
  onSelectTab: (tab: TabId) => void;
  status: SessionStatus;
  wsConnected: boolean;
}

const STATUS_STYLE: Record<SessionStatus, string> = {
  idle: "bg-slate-800 text-slate-300 border-slate-700",
  running: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  paused: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  stopping: "bg-orange-500/15 text-orange-300 border-orange-500/40",
  error: "bg-rose-500/15 text-rose-300 border-rose-500/40",
};

export function TopNav({ activeTab, onSelectTab, status, wsConnected }: TopNavProps) {
  const { locale, toggleLocale, t } = useI18n();

  const statusLabel = {
    idle: t("statusIdle"),
    running: t("statusRunning"),
    paused: t("statusPaused"),
    stopping: t("statusStopping"),
    error: t("statusError"),
  }[status];

  const tabs: { id: TabId; label: string; icon: typeof Activity }[] = [
    { id: "cockpit", label: t("navCockpit"), icon: Activity },
    { id: "replay", label: t("navReplay"), icon: History },
    { id: "settings", label: t("navSettings"), icon: Settings },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-amber-500/25 to-rose-500/20 text-amber-300 ring-1 ring-amber-500/40">
            <Swords className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-slate-100">SpireMind</span>
              <span className="rounded-md bg-slate-800/90 px-1.5 py-0.5 text-[10px] font-medium text-amber-300 ring-1 ring-amber-500/30">
                STS2 Agent
              </span>
            </div>
            <p className="text-xs text-slate-400">{t("brandSubtitle")}</p>
          </div>
        </div>

        <nav className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/70 p-1">
          {tabs.map(({ id, label, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => onSelectTab(id)}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition ${
                  active
                    ? "bg-amber-500/20 text-amber-200 ring-1 ring-amber-500/40"
                    : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-200"
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>

        <div className="flex items-center gap-2.5">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${STATUS_STYLE[status]}`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                status === "running"
                  ? "animate-pulse bg-emerald-400"
                  : status === "error"
                    ? "bg-rose-400"
                    : status === "paused"
                      ? "bg-amber-400"
                      : "bg-slate-400"
              }`}
            />
            {statusLabel}
          </span>

          <span
            title={wsConnected ? t("wsConnected") : t("wsReconnecting")}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
              wsConnected
                ? "border-sky-500/30 bg-sky-500/10 text-sky-300"
                : "border-slate-700 bg-slate-900 text-slate-400"
            }`}
          >
            {wsConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
            <span className="hidden sm:inline">
              {wsConnected ? t("wsConnected") : t("wsReconnecting")}
            </span>
          </span>

          <button
            type="button"
            onClick={toggleLocale}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700/80 bg-slate-900 px-2.5 py-1 text-xs font-medium text-slate-200 transition hover:border-amber-500/50 hover:text-amber-200"
          >
            <Languages className="h-3.5 w-3.5 text-amber-300" />
            <span>{locale === "zh" ? "中文 / EN" : "EN / 中文"}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
