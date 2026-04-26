import { describe, expect, it } from "vitest";
import { bumpAppVersion, compareSimpleSemVer } from "./appStudioVersion";

describe("bumpAppVersion", () => {
  it("bumps patch, minor, and major versions", () => {
    expect(bumpAppVersion("1.2.3", "patch", "")).toEqual({ version: "1.2.4" });
    expect(bumpAppVersion("1.2.3", "minor", "")).toEqual({ version: "1.3.0" });
    expect(bumpAppVersion("1.2.3", "major", "")).toEqual({ version: "2.0.0" });
  });

  it("uses manual version and warns for empty manual input", () => {
    expect(bumpAppVersion("1.2.3", "manual", "2.0.0")).toEqual({ version: "2.0.0" });
    expect(bumpAppVersion("1.2.3", "manual", "").warning).toBeTruthy();
  });

  it("warns instead of throwing for non-semver current versions", () => {
    const result = bumpAppVersion("release-a", "patch", "");
    expect(result.version).toBe("release-a");
    expect(result.warning).toBeTruthy();
  });
});

describe("compareSimpleSemVer", () => {
  it("compares simple semver values", () => {
    expect(compareSimpleSemVer("1.2.3", "1.2.4")).toBe(-1);
    expect(compareSimpleSemVer("1.2.3", "1.2.3")).toBe(0);
    expect(compareSimpleSemVer("2.0.0", "1.9.9")).toBe(1);
    expect(compareSimpleSemVer("bad", "1.0.0")).toBeNull();
  });
});
