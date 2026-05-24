import { useEffect, useMemo, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Download, RefreshCw, ShieldCheck } from "lucide-react";
import launcherPackage from "../package.json";
import { AdminEntryDialog } from "./components/admin/AdminEntryDialog";
import { AppDetailDialog } from "./components/AppDetailDialog";
import { AppGrid } from "./components/AppGrid";
import { CategorySidebar } from "./components/CategorySidebar";
import { LaunchProgressDialog } from "./components/LaunchProgressDialog";
import { SearchBox } from "./components/SearchBox";
import { UpdateNotice } from "./components/UpdateNotice";
import { UpdateSummaryDialog } from "./components/UpdateSummaryDialog";
import { ALL_CATEGORY_FILTER, enabledApps, getCategoryGroups } from "./lib/appCatalog";
import { checkUpdatesRemote, launchApp, listApps } from "./lib/api";
import { filterApps } from "./lib/search";
import type { LaunchEvent, RunStatus, ToolApp } from "./lib/types";
import type { UpdateSummary } from "./lib/updateTypes";
import { shouldShowUserUpdateNotice, updateNoticeKey } from "./lib/updateNotice";

type UpdateStatus = "checking" | "latest" | "available" | "failed";
const UPDATE_NOTICE_DISMISSED_KEY = "toolhub.updateNotice.dismissedKey";
const PACKAGE_TOOLHUB_VERSION = typeof launcherPackage.version === "string" ? launcherPackage.version : "";

export default function App() {
  const [apps, setApps] = useState<ToolApp[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(ALL_CATEGORY_FILTER);
  const [selectedApp, setSelectedApp] = useState<ToolApp | null>(null);
  const [launchAppTarget, setLaunchAppTarget] = useState<ToolApp | null>(null);
  const [launchStatus, setLaunchStatus] = useState<RunStatus>("idle");
  const [launchMessage, setLaunchMessage] = useState("");
  const [launchEvents, setLaunchEvents] = useState<LaunchEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [adminOpen, setAdminOpen] = useState(false);
  const [updateSummary, setUpdateSummary] = useState<UpdateSummary | null>(null);
  const [updateStatus, setUpdateStatus] = useState<UpdateStatus>("checking");
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false);
  const [dismissedUpdateKey, setDismissedUpdateKey] = useState(() => readDismissedUpdateKey());
  const [toolhubVersion, setToolhubVersion] = useState(PACKAGE_TOOLHUB_VERSION);

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
    void checkForUpdates();
  }, []);

  async function checkForUpdates() {
    setUpdateStatus("checking");
    try {
      const summary = await checkUpdatesRemote();
      if (summary.currentVersion) {
        setToolhubVersion(summary.currentVersion);
      }
      setUpdateSummary(summary);
      if (shouldShowUserUpdateNotice(summary)) {
        setUpdateStatus("available");
      } else if (isUpdateCheckFailure(summary)) {
        setUpdateStatus("failed");
      } else {
        setUpdateDialogOpen(false);
        setUpdateStatus("latest");
      }
    } catch (error) {
      setUpdateSummary(null);
      setUpdateDialogOpen(false);
      setUpdateStatus("failed");
      console.error(error);
    }
  }

  const categoryGroups = useMemo(() => getCategoryGroups(apps), [apps]);
  const visibleApps = useMemo(() => filterApps(apps, query, category), [apps, category, query]);
  const isFiltered = query.trim().length > 0 || category !== ALL_CATEGORY_FILTER;
  const visibleUpdateSummary = updateDialogOpen ? updateSummary : null;
  const activeUpdateKey = updateNoticeKey(updateSummary);
  const showUpdateNotice = shouldShowUserUpdateNotice(updateSummary) && activeUpdateKey !== dismissedUpdateKey;

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

  function handleUpdateStatusClick() {
    if (updateSummary) {
      setUpdateDialogOpen(true);
      return;
    }
    void checkForUpdates();
  }

  function handleDismissUpdateNotice() {
    if (activeUpdateKey) {
      setDismissedUpdateKey(activeUpdateKey);
      writeDismissedUpdateKey(activeUpdateKey);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>ToolHub</h1>
          <p>利用する業務アプリを選択してください。</p>
        </div>
        <div className="topbar-actions" aria-label="ToolHubの状態と管理">
          <button
            className={`update-status-button ${updateStatusTone(updateStatus, updateSummary)}`}
            type="button"
            onClick={handleUpdateStatusClick}
            disabled={updateStatus === "checking"}
            title={updateStatusTitle(updateStatus, updateSummary)}
          >
            {renderUpdateStatusIcon(updateStatus, updateSummary)}
            <span>{updateStatusLabel(updateStatus, updateSummary)}</span>
          </button>
          <button className="secondary-button admin-entry-button" type="button" onClick={() => setAdminOpen(true)} title="管理者画面">
            <ShieldCheck size={19} aria-hidden="true" />
            管理者
          </button>
        </div>
      </header>

      <UpdateNotice
        summary={showUpdateNotice ? updateSummary : null}
        onOpen={() => setUpdateDialogOpen(true)}
        onDetails={() => setUpdateDialogOpen(true)}
        onDismiss={handleDismissUpdateNotice}
      />

      <div className="search-row">
        <SearchBox value={query} onChange={setQuery} />
      </div>

      {loadError ? (
        <div className="inline-alert" role="alert">
          <AlertCircle size={20} aria-hidden="true" />
          <span>{loadError}</span>
        </div>
      ) : null}

      <main className="content-layout">
        <CategorySidebar groups={categoryGroups} selected={category} onSelect={setCategory} />
        <section className="workspace">
          <div className="workspace-head">
            <button className="secondary-button workspace-refresh-button" type="button" onClick={() => void loadCatalog()} disabled={loading}>
              <RefreshCw size={16} aria-hidden="true" />
              アプリ一覧更新
            </button>
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
      <AdminEntryDialog open={adminOpen} onClose={() => setAdminOpen(false)} />
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
      {toolhubVersion ? (
        <div className="toolhub-version-badge" aria-label={`ToolHub version ${toolhubVersion}`}>
          ToolHub v{toolhubVersion}
        </div>
      ) : null}
    </div>
  );
}

function readDismissedUpdateKey(): string | null {
  try {
    return window.sessionStorage.getItem(UPDATE_NOTICE_DISMISSED_KEY);
  } catch {
    return null;
  }
}

function writeDismissedUpdateKey(value: string) {
  try {
    window.sessionStorage.setItem(UPDATE_NOTICE_DISMISSED_KEY, value);
  } catch {
    // The banner is still dismissible in memory when WebView storage is unavailable.
  }
}

function updateStatusTone(status: UpdateStatus, summary: UpdateSummary | null): string {
  if (shouldShowUserUpdateNotice(summary)) {
    return "available";
  }
  return status;
}

function updateStatusLabel(status: UpdateStatus, summary: UpdateSummary | null): string {
  if (shouldShowUserUpdateNotice(summary)) {
    return "更新候補あり";
  }
  switch (status) {
    case "checking":
      return "確認中";
    case "failed":
      return "更新確認失敗";
    case "latest":
    case "available":
    default:
      return "最新";
  }
}

function updateStatusTitle(status: UpdateStatus, summary: UpdateSummary | null): string {
  if (shouldShowUserUpdateNotice(summary)) {
    return "更新候補の詳細を確認";
  }
  if (status === "failed") {
    return "更新確認の詳細を確認";
  }
  return "更新状態を確認";
}

function renderUpdateStatusIcon(status: UpdateStatus, summary: UpdateSummary | null) {
  if (shouldShowUserUpdateNotice(summary)) {
    return <Download size={17} aria-hidden="true" />;
  }
  if (status === "checking") {
    return <RefreshCw size={17} aria-hidden="true" />;
  }
  if (status === "failed") {
    return <AlertTriangle size={17} aria-hidden="true" />;
  }
  return <CheckCircle2 size={17} aria-hidden="true" />;
}

function isUpdateCheckFailure(summary: UpdateSummary | null): boolean {
  const status = summary?.status ?? "";
  return status === "source_not_configured" || status === "remote_manifest_fetch_failed" || status.includes("failed");
}
