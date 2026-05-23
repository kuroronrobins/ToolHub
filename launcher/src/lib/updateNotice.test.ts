import { describe, expect, it } from "vitest";
import { shouldShowUserUpdateNotice, updateNoticeKey, updateNoticeTargetLabel } from "./updateNotice";
import type { UpdateSummary } from "./updateTypes";

function summary(partial: Partial<UpdateSummary>): UpdateSummary {
  return {
    title: "更新候補があります",
    message: "新しいToolHubを利用できます。",
    status: "update_available",
    apps: [],
    runtimeUpdate: false,
    ...partial
  };
}

describe("updateNotice", () => {
  it("shows only update_available summaries", () => {
    expect(shouldShowUserUpdateNotice(summary({ status: "update_available" }))).toBe(true);
    expect(shouldShowUserUpdateNotice(summary({ status: "no_update" }))).toBe(false);
    expect(shouldShowUserUpdateNotice(null)).toBe(false);
  });

  it("builds a dismiss key from current and target versions", () => {
    expect(updateNoticeKey(summary({ currentVersion: "0.1.0", remoteManifestVersion: "0.2.0" }))).toBe("0.1.0->0.2.0");
    expect(updateNoticeKey(summary({ currentVersion: "0.1.0", core: { label: "ToolHub", currentVersion: "0.1.0", nextVersion: "0.2.1" } }))).toBe("0.1.0->0.2.1");
    expect(updateNoticeKey(summary({ status: "no_update", currentVersion: "0.1.0", remoteManifestVersion: "0.2.0" }))).toBeNull();
  });

  it("uses the release target label when available", () => {
    expect(updateNoticeTargetLabel(summary({ remoteManifestVersion: "0.2.0" }))).toBe("version 0.2.0");
    expect(updateNoticeTargetLabel(summary({ core: { label: "ToolHub", currentVersion: "0.1.0", nextVersion: "0.2.1" } }))).toBe("version 0.2.1");
    expect(updateNoticeTargetLabel(summary({}))).toBe("新しいバージョン");
  });
});
