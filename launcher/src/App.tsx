import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Info, RefreshCw, Settings } from "lucide-react";
import { AboutDialog } from "./components/AboutDialog";
import { AppDetailDialog } from "./components/AppDetailDialog";
import { AppGrid } from "./components/AppGrid";
import { CategorySidebar } from "./components/CategorySidebar";
import { LaunchProgressDialog } from "./components/LaunchProgressDialog";
import { SearchBox } from "./components/SearchBox";
import { SystemInfoDialog } from "./components/SystemInfoDialog";
import { UpdateNotice } from "./components/UpdateNotice";
import { UpdateSummaryDialog } from "./components/UpdateSummaryDialog";
import { ALL_CATEGORY, enabledApps, getCategoryList } from "./lib/appCatalog";
import { launchApp, listApps } from "./lib/api";
import { filterApps } from "./lib/search";
import type { LaunchEvent, RunStatus, ToolApp } from "./lib/types";
import type { UpdateSummary } from "./lib/updateTypes";

export default function App() {
  const [apps, setApps] = useState<ToolApp[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(ALL_CATEGORY);
  const [selectedApp, setSelectedApp] = useState<ToolApp | null>(null);
  const [launchAppTarget, setLaunchAppTarget] = useState<ToolApp | null>(null);
  const [launchStatus, setLaunchStatus] = useState<RunStatus>("idle");
  const [launchMessage, setLaunchMessage] = useState("");
  const [launchEvents, setLaunchEvents] = useState<LaunchEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [aboutOpen, setAboutOpen] = useState(false);
  const [systemInfoOpen, setSystemInfoOpen] = useState(false);
  const [updateSummary, setUpdateSummary] = useState<UpdateSummary | null>(null);
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);

  async function loadCatalog() {
    setLoading(true);
    setLoadError("");
    try {
      const result = await listApps();
      setApps(enabledApps(result));
    } catch (error) {
      setLoadError("アプリ一覧を読み込めませんでした。管理者に連絡してください。");
      console.error(error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadCatalog();
  }, []);

  const categories = useMemo(() => getCategoryList(apps), [apps]);
  const visibleApps = useMemo(() => filterApps(apps, query, category), [apps, category, query]);
  const isFiltered = query.trim().length > 0 || category !== ALL_CATEGORY;
  const visibleUpdateSummary = updateDialogOpen ? updateSummary : null;

  async function handleLaunch(app: ToolApp) {
    setLaunchAppTarget(app);
    setLaunchStatus("running");
    setLaunchMessage("起動処理を実行しています。");
    setLaunchEvents([{ type: "status", message: "起動準備をしています。", progress: 10 }]);
    try {
      const result = await launchApp(app.id);
      setLaunchEvents(result.events ?? []);
      setLaunchMessage(result.userMessage);
      setLaunchStatus(result.ok ? "success" : "error");
    } catch (error) {
      setLaunchEvents([]);
      setLaunchMessage("アプリの起動に失敗しました。時間をおいて再実行するか、管理者に連絡してください。");
      setLaunchStatus("error");
      console.error(error);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>ToolHub</h1>
          <p>利用する業務アプリを選択してください。</p>
        </div>
        <div className="topbar-actions">
          <button className="secondary-button refresh-button" type="button" onClick={() => void loadCatalog()} title="アプリ一覧を更新">
            <RefreshCw size={18} aria-hidden="true" />
            更新
          </button>
          <button className="icon-button" type="button" onClick={() => setAboutOpen(true)} title="ToolHubについて">
            <Info size={19} aria-hidden="true" />
          </button>
          <button className="icon-button" type="button" onClick={() => setSystemInfoOpen(true)} title="システム情報">
            <Settings size={19} aria-hidden="true" />
          </button>
        </div>
      </header>

      <div className="search-row">
        <SearchBox value={query} onChange={setQuery} />
      </div>

      <UpdateNotice
        summary={updateSummary}
        onOpen={() => setUpdateDialogOpen(true)}
        onDismiss={() => setUpdateSummary(null)}
      />

      {loadError ? (
        <div className="inline-alert" role="alert">
          <AlertCircle size={20} aria-hidden="true" />
          <span>{loadError}</span>
        </div>
      ) : null}

      <main className="content-layout">
        <CategorySidebar categories={categories} selected={category} onSelect={setCategory} />
        <section className="workspace">
          <div className="workspace-head">
            <p>{loading ? "読み込み中" : `${visibleApps.length} 件`}</p>
          </div>
          {loading ? (
            <div className="loading-state">アプリ一覧を読み込んでいます。</div>
          ) : (
            <AppGrid apps={visibleApps} onLaunch={handleLaunch} onDetail={setSelectedApp} isFiltered={isFiltered} />
          )}
        </section>
      </main>

      <AppDetailDialog app={selectedApp} onClose={() => setSelectedApp(null)} />
      <AboutDialog open={aboutOpen} onClose={() => setAboutOpen(false)} />
      <SystemInfoDialog open={systemInfoOpen} onClose={() => setSystemInfoOpen(false)} />
      <UpdateSummaryDialog summary={visibleUpdateSummary} onClose={() => setUpdateDialogOpen(false)} />
      <LaunchProgressDialog
        app={launchAppTarget}
        status={launchStatus}
        message={launchMessage}
        events={launchEvents}
        onClose={() => {
          setLaunchStatus("idle");
          setLaunchAppTarget(null);
          setLaunchEvents([]);
        }}
      />
    </div>
  );
}
