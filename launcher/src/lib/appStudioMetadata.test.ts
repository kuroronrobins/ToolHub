import { describe, expect, it } from "vitest";
import { cleanEditableMetadata, splitMetadataText } from "./appStudioMetadata";

describe("appStudioMetadata", () => {
  it("splits newline and comma separated metadata", () => {
    expect(splitMetadataText("ops, reports\ncsv\nops")).toEqual(["ops", "reports", "csv"]);
  });

  it("omits empty metadata overrides", () => {
    expect(cleanEditableMetadata({ shortDescription: " ", categories: [] })).toBeUndefined();
  });

  it("keeps non-empty metadata overrides", () => {
    expect(
      cleanEditableMetadata({
        shortDescription: " Short ",
        categories: ["ops", " "],
        keywords: ["tool"],
      }),
    ).toEqual({
      shortDescription: "Short",
      description: "",
      categories: ["ops"],
      keywords: ["tool"],
      examples: [],
      useCases: [],
      inputs: [],
      outputs: [],
      notes: [],
      releaseNotes: [],
      changeSummary: "",
    });
  });
});
