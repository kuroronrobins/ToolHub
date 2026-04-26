import { describe, expect, it } from "vitest";
import { recommendBuildMode } from "./appStudioBuildInfo";

describe("recommendBuildMode", () => {
  it("recommends existing-exe for exe entries", () => {
    const result = recommendBuildMode("C:\\work\\tool\\main3.exe");
    expect(result.mode).toBe("existing-exe");
    expect(result.entryKind).toBe("exe");
  });

  it("recommends auto for generic python project entries", () => {
    expect(recommendBuildMode("C:\\work\\tool\\main.py").mode).toBe("auto");
    expect(recommendBuildMode("C:\\work\\tool\\app.py").mode).toBe("auto");
  });

  it("recommends app-env for specific python scripts", () => {
    const result = recommendBuildMode("C:\\work\\tool\\merge_csv.py");
    expect(result.mode).toBe("app-env");
    expect(result.entryKind).toBe("python-script");
  });

  it("falls back to auto for unknown entries", () => {
    expect(recommendBuildMode("C:\\work\\tool\\README.md").mode).toBe("auto");
    expect(recommendBuildMode("").mode).toBe("auto");
  });
});
