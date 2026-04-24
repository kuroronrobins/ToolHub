export interface UpdateItem {
  label: string;
  currentVersion: string;
  nextVersion: string;
}

export interface UpdateSummary {
  title: string;
  message: string;
  core?: UpdateItem;
  runner?: UpdateItem;
  apps: UpdateItem[];
  runtimeUpdate: boolean;
}

