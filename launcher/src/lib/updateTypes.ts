export interface UpdateItem {
  label: string;
  currentVersion: string;
  nextVersion: string;
}

export interface UpdateReleaseNotesUser {
  title?: string | null;
  summary?: string | null;
  highlights?: string[];
  addedApps?: string[];
  recommended?: boolean | null;
}

export interface UpdateReleaseNotesAdmin {
  summary?: string | null;
  changes?: string[];
  validation?: string[];
}

export interface UpdateReleaseNotes {
  schemaVersion?: number | null;
  generatedBy?: string | null;
  editedByAdmin?: boolean | null;
  user?: UpdateReleaseNotesUser | null;
  admin?: UpdateReleaseNotesAdmin | null;
}

export interface UpdateSummary {
  title: string;
  message: string;
  status?:
    | "source_not_configured"
    | "update_available"
    | "no_update"
    | "remote_manifest_fetch_failed"
    | string;
  currentVersion?: string;
  localManifestVersion?: string | null;
  updateSourceConfigured?: boolean;
  updateSourceUrl?: string | null;
  configSource?: "user" | "default" | "missing" | string;
  configPath?: string | null;
  localManifestPath?: string;
  appManifestPath?: string;
  remoteManifestVersion?: string | null;
  remoteManifestUrl?: string | null;
  installerFile?: string | null;
  installerUrl?: string | null;
  installerSha256?: string | null;
  installerSize?: number | null;
  releaseNotes?: UpdateReleaseNotes | null;
  updateCachePath?: string | null;
  lastUpdateResult?: unknown | null;
  core?: UpdateItem;
  runner?: UpdateItem;
  apps: UpdateItem[];
  runtimeUpdate: boolean;
  notes?: string[];
  unsupportedActions?: string[];
}

export interface UpdateDownloadRequest {
  manifestUrl?: string | null;
  installerUrl: string;
  installerFile?: string | null;
  expectedSha256: string;
  expectedSize?: number | null;
}

export interface UpdateDownloadResult {
  ok: boolean;
  status: string;
  message: string;
  failureReason?: string | null;
  checkedAt: string;
  manifestUrl?: string | null;
  installerUrl: string;
  sourceKind: string;
  localTestSource: boolean;
  cachePath?: string | null;
  expectedSha256: string;
  actualSha256?: string | null;
  expectedSize?: number | null;
  actualSize?: number | null;
  verified: boolean;
}

export interface UpdateLaunchRequest {
  cachePath: string;
  expectedSha256: string;
  targetVersion?: string | null;
}

export interface UpdateLaunchResult {
  ok: boolean;
  status: string;
  message: string;
  failureReason?: string | null;
  checkedAt: string;
  currentVersion: string;
  targetVersion?: string | null;
  cachePath: string;
  sourceKind: string;
  expectedSha256: string;
  actualSha256?: string | null;
  verified: boolean;
}

