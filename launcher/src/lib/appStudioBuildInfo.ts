import type { AppStudioBuildMode } from "./appStudioTypes";

export interface BuildModeInfo {
  mode: AppStudioBuildMode;
  title: string;
  description: string;
}

export interface BuildModeRecommendation {
  mode: AppStudioBuildMode;
  reason: string;
  entryKind: "exe" | "python-project" | "python-script" | "unknown";
}

export const BUILD_MODE_INFO: Record<AppStudioBuildMode, BuildModeInfo> = {
  auto: {
    mode: "auto",
    title: "auto",
    description:
      "通常はこれを選びます。Entryの種類からApp Studioが自動判定します。.exeならexisting-exe、軽量Pythonならapp-env、複雑Pythonならfrozen-folderを提案します。迷った場合はauto推奨です。",
  },
  "app-env": {
    mode: "app-env",
    title: "app-env",
    description:
      "PythonソースをToolHub同梱Pythonとアプリ別環境 runtime/app_envs/<app_id> で起動します。単一スクリプトや中規模Pythonツール向けです。ユーザーPCにPythonを入れる必要はありません。requirements.lock生成やapp_env作成と組み合わせるのが推奨です。",
  },
  "frozen-folder": {
    mode: "frozen-folder",
    title: "frozen-folder",
    description:
      "複雑なPythonアプリをPyInstaller --onedir 形式で展開済みフォルダとして配布します。AgendaSnapのようなGUI、音声、外部依存、複数ファイル構成のアプリ向けです。単一exe方式ではなく、展開済みフォルダ方式なので起動を速くしやすいです。",
  },
  "existing-exe": {
    mode: "existing-exe",
    title: "existing-exe",
    description:
      "すでに.exeがあるアプリを登録します。exeと同じフォルダにあるDLL、設定ファイル、補助ファイルも一緒にbin配下へコピーする想定です。Python解析やrequirements解析は基本的に不要です。既存exeをToolHubに登録したい場合に選びます。",
  },
};

const GENERIC_PYTHON_ENTRIES = new Set(["main", "app", "__main__", "launcher", "run"]);

export function recommendBuildMode(entry: string): BuildModeRecommendation {
  const normalized = entry.trim().toLowerCase();
  if (!normalized) {
    return {
      mode: "auto",
      entryKind: "unknown",
      reason: "Entryが未入力です。まずEntryを指定し、迷う場合はautoでSuggestしてください。",
    };
  }
  if (normalized.endsWith(".exe")) {
    return {
      mode: "existing-exe",
      entryKind: "exe",
      reason: "Entryがすでに実行ファイルです。このEntryではexisting-exeが適切です。",
    };
  }
  if (normalized.endsWith(".py")) {
    const stem = stripExtension(lastPathSegment(normalized));
    if (GENERIC_PYTHON_ENTRIES.has(stem)) {
      return {
        mode: "auto",
        entryKind: "python-project",
        reason: "Pythonソースです。main.py/app.py系はプロジェクト構成を見てapp-envかfrozen-folderを判定するため、auto推奨です。",
      };
    }
    return {
      mode: "app-env",
      entryKind: "python-script",
      reason: "Pythonソースです。単一スクリプトらしいEntryなので、軽量Pythonツールとしてapp-envが扱いやすいです。",
    };
  }
  return {
    mode: "auto",
    entryKind: "unknown",
    reason: "Entryの種類を判定できません。まずautoでSuggestし、判定結果を確認してください。",
  };
}

export function buildModeTitle(mode: AppStudioBuildMode): string {
  return BUILD_MODE_INFO[mode].description;
}

function lastPathSegment(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

function stripExtension(fileName: string): string {
  return fileName.replace(/\.[^.]+$/, "");
}
