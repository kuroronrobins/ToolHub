import type { ToolApp } from "./types";
import { appCategoryValues, matchesCategoryFilter } from "./appCatalog";

function normalize(value: string): string {
  return value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function tokenize(query: string): string[] {
  return normalize(query)
    .split(" ")
    .map((token) => token.trim())
    .filter(Boolean);
}

function haystack(app: ToolApp): string {
  return normalize(
    [
      app.name,
      app.shortDescription,
      ...appCategoryValues(app),
      ...app.search.keywords,
      ...app.search.examples
    ].join(" ")
  );
}

export function matchesSearch(app: ToolApp, query: string): boolean {
  const tokens = tokenize(query);
  if (tokens.length === 0) {
    return true;
  }
  const source = haystack(app);
  return tokens.every((token) => source.includes(token));
}

export function filterApps(apps: ToolApp[], query: string, category: string): ToolApp[] {
  return apps.filter((app) => {
    const categoryMatches = matchesCategoryFilter(app, category);
    return categoryMatches && matchesSearch(app, query);
  });
}

