import { describe, expect, it } from "vitest";
import { ALL_CATEGORY, enabledApps, getCategoryList } from "./appCatalog";
import type { ToolApp } from "./types";

function app(id: string, categories: string[], enabled = true): ToolApp {
  return {
    id,
    name: id,
    shortDescription: "desc",
    categories,
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
});

