export type RunStatus = "idle" | "running" | "success" | "error";

export interface AppDetail {
  description: string;
  useCases: string[];
  inputs: string[];
  outputs: string[];
  notes: string[];
}

export interface AppSearch {
  keywords: string[];
  examples: string[];
}

export interface AppAdmin {
  version?: string;
  owner?: string;
  requirements?: string;
  logDir?: string;
}

export interface ToolApp {
  id: string;
  name: string;
  iconSvg?: string;
  shortDescription: string;
  categories: string[];
  detail: AppDetail;
  search: AppSearch;
  admin?: AppAdmin;
  enabled: boolean;
  disabledReason?: string;
}

export interface LaunchEvent {
  type: "status" | "progress" | "success" | "warning" | "error" | "output";
  message: string;
  progress?: number;
}

export interface LaunchResult {
  ok: boolean;
  appId: string;
  userMessage: string;
  logPath?: string;
  events: LaunchEvent[];
}

