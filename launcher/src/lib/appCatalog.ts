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

export function getCategoryCounts(apps: ToolApp[]): Record<string, number> {
  const counts: Record<string, number> = { [ALL_CATEGORY]: apps.length };

  for (const app of apps) {
    const appCategories = new Set<string>();
    for (const category of app.categories) {
      const normalizedCategory = category.trim();
      if (normalizedCategory) {
        appCategories.add(normalizedCategory);
      }
    }

    for (const category of appCategories) {
      counts[category] = (counts[category] ?? 0) + 1;
    }
  }

  return counts;
}

export function enabledApps(apps: ToolApp[]): ToolApp[] {
  return apps.filter((app) => app.enabled);
}

