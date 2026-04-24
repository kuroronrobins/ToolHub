import type { ToolApp } from "./types";

export const ALL_CATEGORY = "すべて";

export function getCategoryList(apps: ToolApp[]): string[] {
  const categories = new Set<string>();
  for (const app of apps) {
    for (const category of app.categories) {
      if (category.trim()) {
        categories.add(category.trim());
      }
    }
  }
  return [ALL_CATEGORY, ...Array.from(categories).sort((a, b) => a.localeCompare(b, "ja"))];
}

export function enabledApps(apps: ToolApp[]): ToolApp[] {
  return apps.filter((app) => app.enabled);
}

