import { describe, expect, it } from "vitest";
import { cleanEditableMetadata, cleanIconOverride, generatedMetadataSuggestion, splitMetadataText } from "./appStudioMetadata";

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

  it("only exposes metadata suggestions when AI generation succeeded", () => {
    const suggestion = {
      name: "Generated",
      shortDescription: "Useful description",
      description: "",
      categories: [],
      keywords: [],
      examples: [],
      useCases: [],
      inputs: [],
      outputs: [],
      notes: [],
      releaseNotes: [],
      aiGenerated: true,
    };
    expect(generatedMetadataSuggestion(suggestion)).toBe(suggestion);
    expect(generatedMetadataSuggestion({ ...suggestion, aiGenerated: false })).toBeNull();
    expect(generatedMetadataSuggestion({ ...suggestion, aiGenerated: undefined })).toBeNull();
  });

  it("keeps adopted png icon overrides only when data is present", () => {
    expect(cleanIconOverride({ selectedIconSource: "candidate_png", pngDataUrl: "data:image/png;base64,AAAA" })).toEqual({
      selectedIconSource: "candidate_png",
      pngDataUrl: "data:image/png;base64,AAAA",
    });
    expect(cleanIconOverride({ selectedIconSource: "fallback_png" })).toBeUndefined();
    expect(cleanIconOverride({ selectedIconSource: "default_icon" })).toBeUndefined();
    expect(cleanIconOverride({ selectedIconSource: "uploaded_png", pngDataUrl: "data:image/png;base64,BBBB" })).toEqual({
      selectedIconSource: "uploaded_png",
      pngDataUrl: "data:image/png;base64,BBBB",
    });
    expect(cleanIconOverride({ selectedIconSource: "candidate_png" })).toBeUndefined();
  });
});
