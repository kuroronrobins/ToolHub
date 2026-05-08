import { AlertTriangle, Eye, EyeOff, FileSearch, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  appStudioDeletePlan,
  appStudioFullDeleteApply,
  appStudioManagementListApps,
  appStudioManagementSetEnabled,
} from "../../../lib/appStudioApi";
import type { AppStudioDeletePlan, AppStudioFullDeleteResult, AppStudioManagedApp } from "../../../lib/appStudioTypes";

const STATUS_LABELS: Record<string, string> = {
  active: "表示中",
  disabled_with_source: "非表示",
  disabled_stale: "非表示・ソースなし",
  enabled_missing_source: "表示中・ソースなし",
  source_missing_from_manifest: "未登録ソース",
  invalid_manifest: "定義エラー",
};

const STATUS_CLASS: Record<string, string> = {
  active: "ok",
  disabled_with_source: "muted",
  disabled_stale: "warn",
  enabled_missing_source: "danger",
  source_missing_from_manifest: "warn",
  invalid_manifest: "danger",
};

const RECOMMENDED_ACTION_LABELS: Record<string, string> = {
  active: "一覧から外す場合は非表示にします。完全削除前は削除内容を確認してください。",
  disabled_with_source: "必要なら再表示できます。完全削除前は削除内容を確認してください。",
  disabled_stale: "ソースがない古い登録です。削除内容を確認して整理できます。",
  enabled_missing_source: "表示中ですがソースがありません。非表示にしてから復旧または削除内容を確認してください。",
  source_missing_from_manifest: "公開前にアプリ一覧を再構築してください。",
  invalid_manifest: "表示切り替えや削除前に app.yaml を修正してください。",
};

const WARNING_LABELS: Record<string, string> = {
  invalid_manifest: "app.yaml を読み込めません。内容を修正してください。",
  enabled_missing_source: "表示中ですが apps/<app_id>/app.yaml が見つかりません。",
  disabled_stale: "ソースがない非表示登録です。古い manifest エントリの可能性があります。",
  source_missing_from_manifest: "apps/<app_id>/app.yaml はありますが、公開用 manifest に登録されていません。",
};

const PLAN_WARNING_LABELS: Record<string, string> = {
  "No repository-managed app source, manifest entry, App Pack, or App Studio backup was found.":
    "リポジトリ管理対象のアプリソース、マニフェスト登録、アプリパック、バックアップが見つかりません。",
  "apps/<app_id>/ exists but app.yaml is missing.": "apps/<app_id>/ はありますが app.yaml が見つかりません。",
  "External absolute paths were found in app.yaml and are excluded from deletion.":
    "app.yaml 内の外部絶対パスは削除対象から除外します。",
  "Potential staging artifacts matched only by partial app_id and were excluded from delete targets.":
    "app_id の部分一致だけで見つかった staging 候補は、自動削除の対象から除外します。",
};

const TARGET_CATEGORY_LABELS: Record<string, string> = {
  managed_required: "必須",
  managed_generated: "生成物",
  managed_generated_candidate: "候補",
  managed_history: "履歴",
  external_reference: "外部参照",
  user_data: "ユーザーデータ",
  shared_runtime: "共有実行環境",
};

const TARGET_ACTION_LABELS: Record<string, string> = {
  "delete apps/<app_id>/": "アプリソースを削除",
  "remove app_manifest entry": "マニフェスト登録を削除",
  "delete App Pack zip": "アプリパックを削除",
  "delete staging artifact": "公開準備生成物を削除",
  "review staging candidate": "公開準備候補を確認",
  "delete runtime app_env": "アプリ用実行環境を削除",
  "delete App Studio backup": "アプリスタジオバックアップを削除",
  "delete legacy lifecycle backup": "旧バックアップを削除",
  "exclude shared runtime": "共有実行環境は除外",
};

const TARGET_NOTE_LABELS: Record<string, string> = {
  "Application source of truth. Future full delete removes it.": "アプリ本体です。完全削除では削除対象になります。",
  "release/app_manifest.json is a generated index; future full delete removes only this app entry.":
    "release/app_manifest.json は索引です。このアプリの登録行だけを削除します。",
  "Generated App Pack for this app.": "このアプリ用に生成されたアプリパックです。",
  "Generated release staging artifact for this app.": "このアプリ用の公開準備生成物です。",
  "Name contains app_id but does not match strict staging rules; future delete must not remove it automatically.":
    "名前に app_id を含みますが所有判定が弱いため、自動削除しません。",
  "App-specific runtime environment. Shared runtimes are excluded.": "このアプリ専用の実行環境です。",
  "Repository-local app backup/history for this app.": "リポジトリ内のアプリバックアップです。",
  "Repository-local legacy lifecycle backup/history for this app.": "リポジトリ内の旧バックアップです。",
  "Shared runtime is not app-owned.": "共有実行環境はアプリ専有ではないため除外します。",
};

const RESULT_STATUS_LABELS: Record<string, string> = {
  deleted: "削除済み",
  already_clean: "処理不要",
  skipped: "スキップ",
  failed: "失敗",
};

const BACKEND_MESSAGE_LABELS: Record<string, string> = {
  "apps/<app_id>/app.yaml is required before showing the app.": "表示に戻すには apps/<app_id>/app.yaml が必要です。",
  "release/app_manifest.json has no entry for this app. Rebuild the app manifest first.":
    "このアプリは release/app_manifest.json に登録されていません。先にアプリ一覧を再構築してください。",
  "Display the deletion plan before running full delete.": "完全削除の前に削除内容を確認してください。",
  "The deletion plan has blocking reasons.": "削除内容にブロック理由があります。",
  "This app state is not supported for full delete.": "このアプリ状態では完全削除を実行できません。",
  "Permanently remove repo-managed targets for this app.": "このアプリのリポジトリ管理対象を完全削除します。",
};

export function AppStudioDeleteManager() {
  const [apps, setApps] = useState<AppStudioManagedApp[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<AppStudioDeletePlan | null>(null);
  const [lastDeleteResult, setLastDeleteResult] = useState<AppStudioFullDeleteResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void reload();
  }, []);

  async function reload() {
    setLoading(true);
    setError("");
    try {
      setApps(await appStudioManagementListApps());
      setLastDeleteResult(null);
    } catch (loadError) {
      setError(errorMessage(loadError, "アプリ管理情報を読み込めませんでした。"));
    } finally {
      setLoading(false);
    }
  }

  async function runSetEnabled(app: AppStudioManagedApp, enabled: boolean) {
    setBusy(`${app.appId}:enabled`);
    setError("");
    setMessage("");
    try {
      const result = await appStudioManagementSetEnabled(app.appId, enabled);
      setMessage(`${app.name} を${enabled ? "表示" : "非表示"}にしました。`);
      setApps(result.apps);
      setLastDeleteResult(null);
      if (selectedPlan?.appId === app.appId) {
        setSelectedPlan(await appStudioDeletePlan(app.appId));
      }
    } catch (actionError) {
      setError(errorMessage(actionError, enabled ? "アプリを表示に戻せませんでした。" : "アプリを非表示にできませんでした。"));
    } finally {
      setBusy("");
    }
  }

  async function showPlan(app: AppStudioManagedApp) {
    setBusy(`${app.appId}:plan`);
    setError("");
    setMessage("");
    try {
      setSelectedPlan(await appStudioDeletePlan(app.appId));
      setLastDeleteResult(null);
    } catch (planError) {
      setError(errorMessage(planError, "削除内容を確認できませんでした。"));
    } finally {
      setBusy("");
    }
  }

  async function runFullDelete(app: AppStudioManagedApp) {
    if (!selectedPlan || selectedPlan.appId !== app.appId) {
      setError("完全削除の前に削除内容を確認してください。");
      return;
    }
    setBusy(`${app.appId}:delete`);
    setError("");
    setMessage("");
    setLastDeleteResult(null);
    try {
      const result = await appStudioFullDeleteApply(app.appId, selectedPlan);
      setApps(result.apps);
      setLastDeleteResult(result);
      if (result.ok) {
        setMessage(`${app.appId} のリポジトリ管理対象を削除しました。`);
        setSelectedPlan(null);
      } else {
        setError(fullDeleteFailureMessage(result));
      }
    } catch (deleteError) {
      setError(errorMessage(deleteError, "完全削除は実行されませんでした。"));
    } finally {
      setBusy("");
    }
  }

  const counts = useMemo(() => {
    return apps.reduce<Record<string, number>>((acc, app) => {
      acc[app.managementStatus] = (acc[app.managementStatus] ?? 0) + 1;
      return acc;
    }, {});
  }, [apps]);

  return (
    <section className="studio-delete">
      <div className="studio-delete-head">
        <div>
          <h4>アプリ削除管理</h4>
          <p>
            アプリ本体は <code>apps/&lt;app_id&gt;/</code> を正とします。この画面では一覧表示の切り替えと、
            リポジトリ管理対象だけの完全削除を扱います。完全削除は削除内容を表示し、安全確認を通過した場合だけ実行できます。
          </p>
        </div>
        <button className="secondary-button" type="button" onClick={() => void reload()} disabled={loading || !!busy}>
          <RefreshCw size={17} aria-hidden="true" />
          再読み込み
        </button>
      </div>

      <div className="studio-delete-summary">
        {Object.entries(counts).map(([status, count]) => (
          <span key={status} className={`studio-delete-pill ${STATUS_CLASS[status] ?? "muted"}`}>
            {statusLabel(status)}: {count}
          </span>
        ))}
      </div>

      {message ? <p className="admin-success">{message}</p> : null}
      {error ? (
        <p className="admin-error">
          <AlertTriangle size={16} aria-hidden="true" />
          {error}
        </p>
      ) : null}

      <div className="studio-delete-table-wrap">
        <table className="studio-delete-table">
          <colgroup>
            <col className="studio-delete-col-status" />
            <col className="studio-delete-col-app" />
            <col className="studio-delete-col-version" />
            <col className="studio-delete-col-config" />
            <col className="studio-delete-col-plan" />
            <col className="studio-delete-col-actions" />
          </colgroup>
          <thead>
            <tr>
              <th>状態</th>
              <th>アプリ</th>
              <th>版</th>
              <th>構成</th>
              <th>削除対象</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {apps.map((app) => (
              <tr key={app.appId}>
                <td>
                  <span
                    className={`studio-delete-pill ${STATUS_CLASS[app.managementStatus] ?? "muted"}`}
                    title={recommendedActionLabel(app.managementStatus)}
                  >
                    {statusLabel(app.managementStatus)}
                  </span>
                </td>
                <td className="studio-delete-app-cell">
                  <div className="studio-delete-app-main">
                    <div className="studio-delete-app-title">
                      <strong>{app.name}</strong>
                      <code>{app.appId}</code>
                    </div>
                    {warningLabel(app) ? <small>{warningLabel(app)}</small> : null}
                  </div>
                </td>
                <td>{app.version ?? "-"}</td>
                <td>
                  <div className="studio-delete-config-list">
                    <span className={`studio-delete-mini-pill ${app.enabled ? "ok" : "muted"}`}>
                      {visibilityLabel(app.enabled)}
                    </span>
                    <span className={`studio-delete-mini-pill ${app.hasSource ? "ok" : "danger"}`}>
                      ソース{app.hasSource ? "あり" : "なし"}
                    </span>
                    <span className={`studio-delete-mini-pill ${app.packageExists ? "ok" : "muted"}`}>
                      パック{app.packageExists ? "あり" : "なし"}
                    </span>
                  </div>
                </td>
                <td className="studio-delete-plan-cell">
                  <span>
                    <strong>{app.deleteTargetCount}</strong>件
                  </span>
                  <small>除外 {app.excludedTargetCount} 件</small>
                </td>
                <td className="studio-delete-actions-cell">
                  <div className="studio-delete-row-actions" aria-label={`${app.name} の操作`}>
                    {app.enabled ? (
                      <button
                        className="icon-button studio-delete-action-button"
                        type="button"
                        disabled={busy !== ""}
                        title="一覧で非表示にする"
                        aria-label={`${app.name} を一覧で非表示にする`}
                        onClick={() => void runSetEnabled(app, false)}
                      >
                        <EyeOff size={16} aria-hidden="true" />
                      </button>
                    ) : app.enabled === false && app.hasSource ? (
                      <button
                        className="icon-button studio-delete-action-button primary"
                        type="button"
                        disabled={busy !== ""}
                        title="一覧に表示する"
                        aria-label={`${app.name} を一覧に表示する`}
                        onClick={() => void runSetEnabled(app, true)}
                      >
                        <Eye size={16} aria-hidden="true" />
                      </button>
                    ) : null}
                    <button
                      className="icon-button studio-delete-action-button"
                      type="button"
                      disabled={busy !== ""}
                      title="削除内容を確認"
                      aria-label={`${app.name} の削除内容を確認する`}
                      onClick={() => void showPlan(app)}
                    >
                      <FileSearch size={16} aria-hidden="true" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!apps.length && !loading ? (
              <tr>
                <td colSpan={6}>管理対象のアプリはありません。</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {selectedPlan ? (
        <DeletionPlanPanel
          plan={selectedPlan}
          busy={busy === `${selectedPlan.appId}:delete`}
          deleteEnabled={canRunFullDelete(apps.find((app) => app.appId === selectedPlan.appId), selectedPlan)}
          onDelete={() => {
            const app = apps.find((candidate) => candidate.appId === selectedPlan.appId);
            if (app) {
              void runFullDelete(app);
            }
          }}
        />
      ) : null}
      {lastDeleteResult ? <FullDeleteResultPanel result={lastDeleteResult} /> : null}
    </section>
  );
}

function DeletionPlanPanel({
  plan,
  busy,
  deleteEnabled,
  onDelete,
}: {
  plan: AppStudioDeletePlan;
  busy: boolean;
  deleteEnabled: boolean;
  onDelete: () => void;
}) {
  return (
    <section className="studio-delete-plan">
      <div className="studio-delete-plan-head">
        <div>
          <h5>削除確認: {plan.appId}</h5>
          <p>
            完全削除で消すのはリポジトリ管理対象だけです。外部参照、ユーザーデータ、共有実行環境、所有判定が弱い公開準備候補は除外します。
            マニフェストはファイル削除ではなく、このアプリの登録行だけを削除します。
          </p>
        </div>
        <button className="secondary-button danger-button" type="button" disabled={!deleteEnabled || busy} onClick={onDelete}>
          <Trash2 size={16} aria-hidden="true" />
          {busy ? "削除中..." : "完全削除を実行"}
        </button>
      </div>

      <div className="studio-delete-plan-grid">
        <PlanMetric label="マニフェスト登録" value={yesNo(plan.manifestEntryExists)} />
        <PlanMetric label="一覧表示" value={visibilityLabel(plan.manifestEnabled)} />
        <PlanMetric label="版" value={plan.manifestVersion ?? "-"} />
        <PlanMetric label="削除対象" value={`${plan.deleteTargets.length}件`} />
        <PlanMetric label="除外対象" value={`${plan.excludedTargets.length}件`} />
        <PlanMetric label="公開準備候補" value={`${plan.stagingCandidatePaths.length}件`} />
      </div>

      {plan.warnings.length ? (
        <div className="admin-warning">
          {plan.warnings.map((warning) => (
            <div key={warning}>{planWarningLabel(warning)}</div>
          ))}
        </div>
      ) : null}

      {plan.blockingReasons.length ? (
        <div className="admin-error">
          {plan.blockingReasons.map((reason) => (
            <div key={reason}>{planWarningLabel(reason)}</div>
          ))}
        </div>
      ) : null}

      <details open className="admin-details">
        <summary>削除対象</summary>
        <TargetList targets={plan.deleteTargets} />
      </details>

      <details className="admin-details">
        <summary>除外対象</summary>
        <TargetList targets={plan.excludedTargets} />
      </details>
    </section>
  );
}

function FullDeleteResultPanel({ result }: { result: AppStudioFullDeleteResult }) {
  return (
    <section className="studio-delete-plan">
      <div className="studio-delete-plan-head">
        <div>
          <h5>完全削除結果: {result.appId}</h5>
          <p>{result.ok ? "リポジトリ管理対象の削除が完了しました。" : "完全削除は完了しませんでした。失敗または残存対象を確認してください。"}</p>
        </div>
        <span className={`studio-delete-pill ${result.ok ? "ok" : "danger"}`}>{result.ok ? "完了" : "要確認"}</span>
      </div>
      <div className="studio-delete-plan-grid">
        <PlanMetric label="削除済み" value={`${result.deleted.length}件`} />
        <PlanMetric label="処理不要" value={`${result.alreadyClean.length}件`} />
        <PlanMetric label="失敗" value={`${result.failed.length}件`} />
        <PlanMetric label="マニフェスト登録削除" value={yesNo(result.manifestEntryRemoved)} />
        <PlanMetric label="残存対象" value={`${result.postCheckSummary.remainingDeleteTargetCount}件`} />
      </div>
      {result.failed.length ? (
        <details open className="admin-details">
          <summary>失敗した対象</summary>
          <ResultRecordList records={result.failed} />
        </details>
      ) : null}
      <details className="admin-details">
        <summary>削除済み対象</summary>
        <ResultRecordList records={result.deleted} />
      </details>
      <details className="admin-details">
        <summary>保持した除外対象</summary>
        <TargetList targets={result.excluded} />
      </details>
    </section>
  );
}

function PlanMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TargetList({ targets }: { targets: AppStudioDeletePlan["deleteTargets"] }) {
  if (!targets.length) {
    return <p className="admin-muted">対象はありません。</p>;
  }
  return (
    <div className="studio-delete-target-list">
      {targets.map((target) => (
        <div key={`${target.category}:${target.path}:${target.action}`} className="studio-delete-target-row">
          <span className={`studio-delete-pill ${target.deleteAllowed ? "warn" : "muted"}`}>
            {targetCategoryLabel(target.category)}
          </span>
          <div>
            <strong>{targetActionLabel(target.action)}</strong>
            <code>{target.path}</code>
            <small>
              {target.exists ? "存在" : "未作成"} / {targetNoteLabel(target.note)}
            </small>
          </div>
        </div>
      ))}
    </div>
  );
}

function ResultRecordList({ records }: { records: AppStudioFullDeleteResult["deleted"] }) {
  if (!records.length) {
    return <p className="admin-muted">記録はありません。</p>;
  }
  return (
    <div className="studio-delete-target-list">
      {records.map((record) => (
        <div key={`${record.status}:${record.comparisonKey}`} className="studio-delete-target-row">
          <span className={`studio-delete-pill ${record.status === "failed" ? "danger" : "warn"}`}>
            {resultStatusLabel(record.status)}
          </span>
          <div>
            <strong>{targetActionLabel(record.action)}</strong>
            <code>{record.path}</code>
            <small>{targetNoteLabel(record.note)}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

function recommendedActionLabel(status: string): string {
  return RECOMMENDED_ACTION_LABELS[status] ?? "状態を確認してください。";
}

function warningLabel(app: AppStudioManagedApp): string {
  if (!app.warning) {
    return "";
  }
  return WARNING_LABELS[app.managementStatus] ?? "確認が必要です。詳細ログを確認してください。";
}

function visibilityLabel(value?: boolean | null): string {
  if (value == null) {
    return "表示不明";
  }
  return value ? "表示中" : "非表示";
}

function yesNo(value: boolean): string {
  return value ? "あり" : "なし";
}

function planWarningLabel(value: string): string {
  return PLAN_WARNING_LABELS[value] ?? value;
}

function targetCategoryLabel(value: string): string {
  return TARGET_CATEGORY_LABELS[value] ?? value;
}

function targetActionLabel(value: string): string {
  return TARGET_ACTION_LABELS[value] ?? value;
}

function targetNoteLabel(value: string): string {
  return TARGET_NOTE_LABELS[value] ?? BACKEND_MESSAGE_LABELS[value] ?? value;
}

function resultStatusLabel(value: string): string {
  return RESULT_STATUS_LABELS[value] ?? value;
}

function backendMessageLabel(value: string): string {
  return BACKEND_MESSAGE_LABELS[value] ?? value;
}

function canRunFullDelete(app: AppStudioManagedApp | undefined, plan: AppStudioDeletePlan | null): boolean {
  if (!app || !plan || plan.appId !== app.appId) {
    return false;
  }
  const supportedStatuses = new Set(["active", "disabled_with_source", "disabled_stale", "enabled_missing_source"]);
  return (
    supportedStatuses.has(app.managementStatus) &&
    plan.blockingReasons.length === 0 &&
    plan.deleteTargets.some((target) => target.deleteAllowed && target.exists)
  );
}

function fullDeleteFailureMessage(result: AppStudioFullDeleteResult): string {
  const failed = result.failed.map((record) => `${targetActionLabel(record.action)}: ${targetNoteLabel(record.note)}`).join(" / ");
  const remaining = result.postCheckSummary.remainingDeleteTargets.join(" / ");
  return [`${result.appId} の完全削除は完了しませんでした。`, failed ? `失敗: ${failed}` : "", remaining ? `残存: ${remaining}` : ""]
    .filter(Boolean)
    .join(" ");
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return `${fallback} ${backendMessageLabel(error.message)}`;
  }
  if (typeof error === "string" && error.trim()) {
    return `${fallback} ${backendMessageLabel(error)}`;
  }
  return fallback;
}
