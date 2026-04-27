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
    title: "legacy auto",
    description: "互換性のために残している旧モードです。通常新規登録では使用しません。",
  },
  "app-env": {
    mode: "app-env",
    title: "legacy app-env",
    description: "互換性のために残している旧モードです。通常新規登録では利用者向け実行方式として使用しません。",
  },
  "frozen-folder": {
    mode: "frozen-folder",
    title: "配布用exe",
    description: "PythonソースからPyInstaller --onedir形式のfrozen-folderを作成し、生成exeをrun.entryとして登録します。",
  },
  "existing-exe": {
    mode: "existing-exe",
    title: "legacy existing-exe",
    description: "互換性のために残している旧モードです。通常新規登録では既存exe登録を扱いません。",
  },
};

const GENERIC_PYTHON_ENTRIES = new Set(["main", "app", "__main__", "launcher", "run"]);

export function recommendBuildMode(entry: string): BuildModeRecommendation {
  const normalized = entry.trim().toLowerCase();
  if (!normalized) {
    return {
      mode: "frozen-folder",
      entryKind: "unknown",
      reason: "通常新規登録はPythonソースからfrozen-folder exeを作成する固定フローです。",
    };
  }
  if (normalized.endsWith(".exe")) {
    return {
      mode: "frozen-folder",
      entryKind: "exe",
      reason: "通常新規登録では既存exeを登録できません。Pythonソースを選択してください。",
    };
  }
  if (normalized.endsWith(".py")) {
    const stem = stripExtension(lastPathSegment(normalized));
    return {
      mode: "frozen-folder",
      entryKind: GENERIC_PYTHON_ENTRIES.has(stem) ? "python-project" : "python-script",
      reason: "Pythonソースを解析し、必要ファイルを同梱したfrozen-folder exeを作成します。",
    };
  }
  return {
    mode: "frozen-folder",
    entryKind: "unknown",
    reason: "通常新規登録ではPythonソースを入力し、frozen-folder exeを作成します。",
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
