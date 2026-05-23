import type { UpdateSummary } from "./updateTypes";

export function shouldShowUserUpdateNotice(summary: UpdateSummary | null): summary is UpdateSummary {
  return summary?.status === "update_available";
}

export function updateNoticeKey(summary: UpdateSummary | null): string | null {
  if (!shouldShowUserUpdateNotice(summary)) {
    return null;
  }
  const target = summary.remoteManifestVersion ?? summary.core?.nextVersion ?? "unknown";
  return `${summary.currentVersion ?? "unknown"}->${target}`;
}

export function updateNoticeTargetLabel(summary: UpdateSummary): string {
  const targetVersion = summary.remoteManifestVersion ?? summary.core?.nextVersion ?? null;
  return targetVersion ? `version ${targetVersion}` : "新しいバージョン";
}
