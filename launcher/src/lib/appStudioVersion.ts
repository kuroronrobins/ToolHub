import type { AppStudioVersionBumpMode } from "./appStudioTypes";

export interface VersionBumpResult {
  version: string;
  warning?: string;
}

export function isSimpleSemVer(version: string): boolean {
  return /^\d+\.\d+\.\d+$/.test(version.trim());
}

export function bumpAppVersion(currentVersion: string, mode: AppStudioVersionBumpMode, manualVersion: string): VersionBumpResult {
  const current = currentVersion.trim();
  if (mode === "manual") {
    const version = manualVersion.trim();
    return {
      version,
      warning: version ? undefined : "Manual version is required.",
    };
  }

  if (!isSimpleSemVer(current)) {
    return {
      version: manualVersion.trim() || current,
      warning: "Current version is not simple SemVer. Use manual version input.",
    };
  }

  const [major, minor, patch] = current.split(".").map((part) => Number.parseInt(part, 10));
  if (mode === "patch") {
    return { version: `${major}.${minor}.${patch + 1}` };
  }
  if (mode === "minor") {
    return { version: `${major}.${minor + 1}.0` };
  }
  return { version: `${major + 1}.0.0` };
}

export function compareSimpleSemVer(left: string, right: string): number | null {
  if (!isSimpleSemVer(left) || !isSimpleSemVer(right)) {
    return null;
  }
  const leftParts = left.split(".").map((part) => Number.parseInt(part, 10));
  const rightParts = right.split(".").map((part) => Number.parseInt(part, 10));
  for (let index = 0; index < 3; index += 1) {
    if (leftParts[index] < rightParts[index]) {
      return -1;
    }
    if (leftParts[index] > rightParts[index]) {
      return 1;
    }
  }
  return 0;
}
