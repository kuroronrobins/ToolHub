export interface UpdateItem {
  label: string;
  currentVersion: string;
  nextVersion: string;
}

export interface UpdateSummary {
  title: string;
  message: string;
  status?: "source_not_configured" | "update_available" | "no_update" | string;
  currentVersion?: string;
  localManifestVersion?: string | null;
  updateSourceConfigured?: boolean;
  updateSourceUrl?: string | null;
  configSource?: "user" | "default" | "missing" | string;
  configPath?: string | null;
  localManifestPath?: string;
  appManifestPath?: string;
  core?: UpdateItem;
  runner?: UpdateItem;
  apps: UpdateItem[];
  runtimeUpdate: boolean;
  notes?: string[];
  unsupportedActions?: string[];
}

