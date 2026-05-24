import type { ToolApp } from "./types";

export const ALL_CATEGORY = "すべて";
export const ALL_CATEGORY_FILTER = "all";

export type CategoryAxis = "user" | "primary" | "target" | "tag" | "legacy";

export interface CategoryFilterItem {
  key: string;
  label: string;
  count: number;
}

export interface CategoryGroup {
  axis: CategoryAxis | "all";
  title: string;
  items: CategoryFilterItem[];
}

export function categoryFilterKey(axis: CategoryAxis, label: string): string {
  return `${axis}:${label}`;
}

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

export function getCategoryGroups(apps: ToolApp[]): CategoryGroup[] {
  const userCategories = countAxisValues(apps, (app) => [appUserCategory(app)]);
  const groups: CategoryGroup[] = [
    {
      axis: "all",
      title: "すべて",
      items: [{ key: ALL_CATEGORY_FILTER, label: ALL_CATEGORY, count: apps.length }],
    },
    { axis: "user", title: "", items: toItems("user", userCategories) },
  ];

  return groups.filter((group) => group.axis === "all" || group.items.length > 0);
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

export function appCategoryValues(app: ToolApp): string[] {
  return cleanList([
    app.primaryCategory ?? "",
    ...(app.targetCategories ?? []),
    ...(app.tags ?? []),
    ...app.categories,
  ]);
}

export function appPrimaryCategory(app: ToolApp): string {
  const value = cleanString(app.primaryCategory);
  if (value) {
    return value;
  }
  return cleanList(app.categories)[0] ?? "その他";
}

export function appUserCategory(app: ToolApp): string {
  return appTargetCategories(app)[0] ?? appPrimaryCategory(app);
}

export function appTargetCategories(app: ToolApp): string[] {
  return cleanList(app.targetCategories);
}

export function appTags(app: ToolApp): string[] {
  return cleanList(app.tags);
}

export function matchesCategoryFilter(app: ToolApp, selected: string): boolean {
  if (selected === ALL_CATEGORY || selected === ALL_CATEGORY_FILTER) {
    return true;
  }
  const [axis, ...rest] = selected.split(":");
  const label = rest.join(":").trim();
  if (!label) {
    return app.categories.includes(selected);
  }
  if (axis === "primary") {
    return appPrimaryCategory(app) === label;
  }
  if (axis === "user") {
    return appUserCategory(app) === label;
  }
  if (axis === "target") {
    return appTargetCategories(app).includes(label);
  }
  if (axis === "tag") {
    return appTags(app).includes(label);
  }
  return app.categories.includes(label);
}

export function enabledApps(apps: ToolApp[]): ToolApp[] {
  return apps.filter((app) => app.enabled);
}

function countAxisValues(apps: ToolApp[], select: (app: ToolApp) => string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const app of apps) {
    const values = new Set(select(app));
    for (const value of values) {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
  }
  return counts;
}

function toItems(axis: CategoryAxis, counts: Map<string, number>): CategoryFilterItem[] {
  return Array.from(counts)
    .sort(([left], [right]) => left.localeCompare(right, "ja"))
    .map(([label, count]) => ({ key: categoryFilterKey(axis, label), label, count }));
}

function cleanList(value?: string[]): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const values: string[] = [];
  for (const item of value) {
    const text = cleanString(item);
    if (text && !values.includes(text)) {
      values.push(text);
    }
  }
  return values;
}

function cleanString(value?: string | null): string {
  return String(value ?? "").trim();
}

