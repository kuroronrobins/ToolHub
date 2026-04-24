import { describe, expect, it } from "vitest";
import { filterApps, matchesSearch } from "./search";
import type { ToolApp } from "./types";

const apps: ToolApp[] = [
  {
    id: "csv",
    name: "CSV結合ツール",
    shortDescription: "複数のCSVをまとめます。",
    categories: ["CSV", "ファイル処理"],
    detail: {
      description: "説明",
      useCases: [],
      inputs: [],
      outputs: [],
      notes: []
    },
    search: {
      keywords: ["結合", "マージ"],
      examples: ["複数ファイルを1つにしたい"]
    },
    enabled: true
  },
  {
    id: "report",
    name: "レポート作成",
    shortDescription: "定型レポートを作成します。",
    categories: ["帳票"],
    detail: {
      description: "説明",
      useCases: [],
      inputs: [],
      outputs: [],
      notes: []
    },
    search: {
      keywords: ["報告書"],
      examples: ["月次資料を作りたい"]
    },
    enabled: true
  }
];

describe("search", () => {
  it("matches Japanese keywords", () => {
    expect(matchesSearch(apps[0], "マージ")).toBe(true);
    expect(matchesSearch(apps[1], "マージ")).toBe(false);
  });

  it("filters by category and query", () => {
    const result = filterApps(apps, "CSV", "ファイル処理");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("csv");
  });
});

