import { describe, expect, it } from "vitest";
import { ALL_CATEGORY, ALL_CATEGORY_FILTER, enabledApps, getCategoryGroups, getCategoryList, matchesCategoryFilter } from "./appCatalog";
import type { ToolApp } from "./types";

function app(id: string, categories: string[], enabled = true): ToolApp {
  return {
    id,
    name: id,
    shortDescription: "desc",
    categories,
    primaryCategory: categories[0],
    targetCategories: [],
    tags: categories.slice(1),
    detail: {
      description: "desc",
      useCases: [],
      inputs: [],
      outputs: [],
      notes: []
    },
    search: {
      keywords: [],
      examples: []
    },
    enabled
  };
}

describe("appCatalog", () => {
  it("extracts categories with all first", () => {
    expect(getCategoryList([app("a", ["帳票"]), app("b", ["CSV", "帳票"])])).toEqual([ALL_CATEGORY, "CSV", "帳票"]);
  });

  it("keeps only enabled apps", () => {
    expect(enabledApps([app("a", ["CSV"]), app("b", ["帳票"], false)]).map((item) => item.id)).toEqual(["a"]);
  });

  it("uses the first target category for the user sidebar", () => {
    const groups = getCategoryGroups([
      {
        ...app("id", ["業務自動化", "COMPASS", "3DX", "ID取得"]),
        primaryCategory: "業務自動化",
        targetCategories: ["COMPASS", "3DX"],
        tags: ["ID取得"]
      },
      {
        ...app("download", ["文書・PDF", "COMPASS", "3DX", "ダウンロード"]),
        primaryCategory: "文書・PDF",
        targetCategories: ["COMPASS", "3DX"],
        tags: ["ダウンロード"]
      },
    ]);

    expect(groups[0].items[0]).toEqual({ key: ALL_CATEGORY_FILTER, label: ALL_CATEGORY, count: 2 });
    expect(groups.map((group) => group.axis)).toEqual(["all", "user"]);
    expect(groups.find((group) => group.axis === "user")?.items).toEqual([{ key: "user:COMPASS", label: "COMPASS", count: 2 }]);
  });

  it("matches selected axis filters", () => {
    const tool = {
      ...app("automation", ["業務自動化", "XCgate", "登録"]),
      primaryCategory: "業務自動化",
      targetCategories: ["XCgate"],
      tags: ["登録"]
    };

    expect(matchesCategoryFilter(tool, "user:XCgate")).toBe(true);
    expect(matchesCategoryFilter(tool, "target:XCgate")).toBe(true);
    expect(matchesCategoryFilter(tool, "target:COMPASS")).toBe(false);
  });
});

