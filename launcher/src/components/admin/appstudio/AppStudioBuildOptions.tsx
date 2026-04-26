import { Info } from "lucide-react";
import { BUILD_MODE_INFO, buildModeTitle, recommendBuildMode } from "../../../lib/appStudioBuildInfo";
import type { AppStudioBuildMode, AppStudioImportRequest } from "../../../lib/appStudioTypes";

interface Props {
  request: AppStudioImportRequest;
  onChange: (next: AppStudioImportRequest) => void;
}

type BuildOptionKey = "generateLock" | "createAppEnv" | "rebuildAppEnv" | "buildFrozenFolder" | "verifyRuntime";

interface BuildOptionInfo {
  key: BuildOptionKey;
  label: string;
  summary: string;
  when: string;
  detail: string;
}

const BUILD_MODES: AppStudioBuildMode[] = ["auto", "app-env", "frozen-folder", "existing-exe"];

const BUILD_OPTIONS: BuildOptionInfo[] = [
  {
    key: "generateLock",
    label: "requirements.lock生成",
    summary: "依存関係を固定して再現性を高めます",
    when: "Python依存を後から再現したい時にON",
    detail: "現在解析できる依存関係をlockファイルとして残します。配布後に同じ環境を作り直しやすくなります。",
  },
  {
    key: "createAppEnv",
    label: "app_env作成",
    summary: "このアプリ専用の実行環境を作ります",
    when: "app-env方式で初回登録する時にON",
    detail: "runtime/app_envs/<app_id> に専用環境を作ります。他アプリの依存関係と混ざりにくくなります。",
  },
  {
    key: "rebuildAppEnv",
    label: "app_env再作成",
    summary: "壊れた/変わった環境を作り直します",
    when: "依存関係を変えた時や環境不調時にON",
    detail: "既存のapp_envを作り直します。通常の初回登録では不要ですが、依存更新や環境破損の切り分けに使います。",
  },
  {
    key: "buildFrozenFolder",
    label: "frozen-folder build",
    summary: "Python不要で配れる実行フォルダを作ります",
    when: "配布先にPython環境を意識させたくない時にON",
    detail: "PyInstaller onedir相当の実行フォルダを作成します。GUIアプリや複数ファイル構成の配布に向いています。",
  },
  {
    key: "verifyRuntime",
    label: "runtime検証",
    summary: "ToolHub同梱runtimeで動くか確認します",
    when: "正式配布前の最終確認でON",
    detail: "開発機のPythonではなく、ToolHub同梱runtimeで実行可能か確認します。配布前の再現性確認に使います。",
  },
];

export function AppStudioBuildOptions({ request, onChange }: Props) {
  const selectedInfo = BUILD_MODE_INFO[request.buildMode];
  const recommendation = recommendBuildMode(request.entry);

  function update(partial: Partial<AppStudioImportRequest>) {
    onChange({ ...request, ...partial });
  }

  return (
    <section className="studio-step studio-build-options">
      <div>
        <span className="studio-step-index">B</span>
        <h4>実行方式</h4>
      </div>
      <div className="studio-segmented" role="radiogroup" aria-label="実行方式">
        {BUILD_MODES.map((mode) => (
          <button
            key={mode}
            type="button"
            className={`${request.buildMode === mode ? "active" : ""} ${recommendation.mode === mode ? "recommended" : ""}`.trim()}
            title={buildModeTitle(mode)}
            onClick={() => update({ buildMode: mode })}
          >
            {mode}
          </button>
        ))}
      </div>

      <div className="studio-build-help">
        <strong>{selectedInfo.title}</strong>
        <p>{selectedInfo.description}</p>
        <div className="studio-build-recommendation">
          <span>推奨: {recommendation.mode}</span>
          <p>{recommendation.reason}</p>
        </div>
        {recommendation.entryKind === "exe" ? (
          <ul>
            <li>既存exeとして登録します。</li>
            <li>Python依存解析は基本的に不要です。</li>
            <li>exeと同じフォルダのDLLや設定ファイルもbin配下にコピーされます。</li>
            <li>dry executionがスキップされてwarnになる場合があります。警告許容モードなら承認できます。</li>
          </ul>
        ) : null}
      </div>

      <div className="studio-option-grid">
        {BUILD_OPTIONS.map((option) => (
          <label className="studio-option-card" key={option.key}>
            <input type="checkbox" checked={Boolean(request[option.key])} onChange={(event) => update({ [option.key]: event.target.checked })} />
            <span className="studio-option-text">
              <span className="studio-option-title">
                <strong>{option.label}</strong>
                <span className="studio-info-icon" title={option.detail} aria-label={`${option.label}の補足`}>
                  <Info size={15} aria-hidden="true" />
                </span>
              </span>
              <small>{option.summary}</small>
              <em>{option.when}</em>
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}
