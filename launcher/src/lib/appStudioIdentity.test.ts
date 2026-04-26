import { describe, expect, it } from "vitest";
import { suggestAppIdentity } from "./appStudioIdentity";

describe("suggestAppIdentity", () => {
  it("uses parent folder for generic main.py", () => {
    expect(suggestAppIdentity("C:\\work\\csv_merge\\main.py")).toEqual({
      appId: "csv_merge",
      name: "Csv Merge",
    });
  });

  it("uses parent folder for generic app.py", () => {
    expect(suggestAppIdentity("C:\\work\\mytool\\app.py")).toEqual({
      appId: "mytool",
      name: "Mytool",
    });
  });

  it("uses file stem for specific scripts", () => {
    expect(suggestAppIdentity("C:\\work\\tools\\merge_csv.py")).toEqual({
      appId: "merge_csv",
      name: "Merge Csv",
    });
  });

  it("falls back safely for non-ascii names", () => {
    expect(suggestAppIdentity("C:\\work\\日本語\\main.py").appId).toBe("app");
  });
});
