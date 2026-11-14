import { useState } from "react";
import { TopNav } from "./components/TopNav";
import { useSessionSocket } from "./hooks/useSessionSocket";
import { I18nProvider } from "./i18n";
import { CockpitPage } from "./pages/CockpitPage";
import { ReplayPage } from "./pages/ReplayPage";
import { SettingsPage } from "./pages/SettingsPage";
import type { TabId } from "./types";

function ConsoleShell() {
  const [activeTab, setActiveTab] = useState<TabId>("cockpit");
  const { snapshot, setSnapshot, wsConnected, refreshSnapshot } = useSessionSocket();

  return (
    <div className="min-h-screen bg-transparent text-slate-100">
      <TopNav
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        status={snapshot.status}
        wsConnected={wsConnected}
      />

      <main className="mx-auto max-w-[1600px] px-4 py-5 sm:px-6">
        {activeTab === "cockpit" && (
          <CockpitPage
            snapshot={snapshot}
            onSnapshotUpdate={setSnapshot}
            onRefreshSnapshot={refreshSnapshot}
          />
        )}
        {activeTab === "replay" && <ReplayPage />}
        {activeTab === "settings" && <SettingsPage sessionStatus={snapshot.status} />}
      </main>
    </div>
  );
}

export function App() {
  return (
    <I18nProvider>
      <ConsoleShell />
    </I18nProvider>
  );
}

export default App;
