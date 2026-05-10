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
    description: "互換性のために残している旧モードです。通常新規登録では使用しません。",
  },
  "shared-env": {
    mode: "shared-env",
    title: "共有ランタイム",
    description: "Pythonソースをsrc/に登録し、requirements.lockに対応する共通のバージョン別Python環境で実行します。",
  },
  "frozen-folder": {
    mode: "frozen-folder",
    title: "legacy frozen-folder",
    description: "互換性のために残している旧モードです。通常新規登録では使用しません。",
  },
  "existing-exe": {
    mode: "existing-exe",
    title: "legacy existing-exe",
    description: "互換性のために残している旧モードです。通常新規登録では使用しません。",
  },
};

const GENERIC_PYTHON_ENTRIES = new Set(["main", "app", "__main__", "launcher", "run"]);

export function recommendBuildMode(entry: string): BuildModeRecommendation {
  const normalized = entry.trim().toLowerCase();
  if (!normalized) {
    return {
      mode: "shared-env",
      entryKind: "unknown",
      reason: "通常新規登録はPythonソースを共通のバージョン別ランタイムで実行する固定フローです。",
    };
  }
  if (normalized.endsWith(".exe")) {
    return {
      mode: "shared-env",
      entryKind: "exe",
      reason: "通常新規登録では既存exeを登録できません。Pythonソースを選択してください。",
    };
  }
  if (normalized.endsWith(".py")) {
    const stem = stripExtension(lastPathSegment(normalized));
    return {
      mode: "shared-env",
      entryKind: GENERIC_PYTHON_ENTRIES.has(stem) ? "python-project" : "python-script",
      reason: "Pythonソースを解析し、同じ依存バージョンのアプリは共通ランタイムを再利用して登録します。",
    };
  }
  return {
    mode: "shared-env",
    entryKind: "unknown",
    reason: "通常新規登録ではPythonソースを入力し、共通ランタイム方式で登録します。",
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
