import { describe, expect, it } from "vitest";
import { recommendBuildMode } from "./appStudioBuildInfo";

describe("recommendBuildMode", () => {
  it("keeps normal new registration fixed to frozen-folder", () => {
    expect(recommendBuildMode("C:\\work\\tool\\main.py").mode).toBe("frozen-folder");
    expect(recommendBuildMode("C:\\work\\tool\\merge_csv.py").mode).toBe("frozen-folder");
    expect(recommendBuildMode("C:\\work\\tool\\README.md").mode).toBe("frozen-folder");
    expect(recommendBuildMode("").mode).toBe("frozen-folder");
  });

  it("does not recommend existing-exe for exe entries", () => {
    const result = recommendBuildMode("C:\\work\\tool\\main3.exe");
    expect(result.mode).toBe("frozen-folder");
    expect(result.entryKind).toBe("exe");
    expect(result.reason).toContain("既存exe");
  });
});
