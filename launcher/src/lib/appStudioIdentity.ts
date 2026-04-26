const GENERIC_ENTRY_NAMES = new Set(["main", "app", "__main__", "launcher", "run"]);

export interface AppIdentitySuggestion {
  appId: string;
  name: string;
}

export function suggestAppIdentity(entry: string): AppIdentitySuggestion {
  const parts = splitPath(entry);
  const fileName = parts[parts.length - 1] ?? "";
  const parentName = parts.length >= 2 ? parts[parts.length - 2] : "";
  const stem = stripExtension(fileName);
  const source = GENERIC_ENTRY_NAMES.has(stem.toLowerCase()) ? parentName || stem : stem;
  return {
    appId: toAppId(source),
    name: toDisplayName(source),
  };
}

export function toAppId(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^[^a-z0-9]+/, "")
    .replace(/[^a-z0-9]+$/, "")
    .slice(0, 64);
  return normalized || "app";
}

export function toDisplayName(value: string): string {
  const cleaned = value.trim().replace(/\.[^.]+$/, "");
  const words = cleaned
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (words.length === 0) {
    return "App";
  }
  return words.map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function splitPath(path: string): string[] {
  return path.replace(/\\/g, "/").split("/").filter(Boolean);
}

function stripExtension(fileName: string): string {
  return fileName.replace(/\.[^.]+$/, "");
}
