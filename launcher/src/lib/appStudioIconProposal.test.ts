import { describe, expect, it } from "vitest";
import {
  iconSourceLabel,
  normalizeAppStudioIconProposal,
  normalizeIconSource,
  previewIconDataUrl,
} from "./appStudioIconProposal";
import type { AppStudioAiIconSuggestion } from "./appStudioTypes";

const PNG_A = "data:image/png;base64,AAAA";
const PNG_B = "data:image/png;base64,BBBB";
const PNG_DEFAULT = "data:image/png;base64,DEFAULT";
const EMPTY_METADATA = {
  categories: [],
  keywords: [],
  examples: [],
  useCases: [],
  inputs: [],
  outputs: [],
  notes: [],
  releaseNotes: [],
};

describe("appStudioIconProposal", () => {
  it("keeps API candidates visible and hides legacy fallback candidates", () => {
    const icon: AppStudioAiIconSuggestion = {
      finalPngDataUrl: PNG_DEFAULT,
      imageApiSummary: {
        apiCandidateCount: 1,
        selectedIconSource: "default_icon",
        defaultIconUsed: true,
        fallbackCandidateCount: 1,
        fallbackCreatedReason: "legacy field only",
        userRevisionInstruction: "make it sharper",
        finalImageApiPrompt: "final image prompt",
      },
      candidates: [
        {
          candidateId: "icon_candidate_2",
          number: 2,
          source: "api_generate",
          fallback: false,
          pngDataUrl: PNG_A,
        },
        {
          candidateId: "legacy_fallback",
          number: 1,
          source: "fallback_png",
          fallback: true,
          pngDataUrl: PNG_B,
        },
      ],
    };

    const normalized = normalizeAppStudioIconProposal(icon);

    expect(normalized.apiCandidates.map((candidate) => candidate.candidateId)).toEqual(["icon_candidate_2"]);
    expect(normalized.legacyCandidates.map((candidate) => candidate.candidateId)).toEqual(["legacy_fallback"]);
    expect(normalized.hiddenLegacyCount).toBe(1);
    expect(normalized.hasAdoptableApiCandidates).toBe(true);
    expect(normalized.canAdoptPrimaryPng).toBe(false);
    expect(normalized.defaultIcon.used).toBe(true);
    expect(normalized.defaultIcon.finalPngDataUrl).toBe(PNG_DEFAULT);
    expect(normalized.revisionPromptInfo).toEqual({
      userRevisionInstruction: "make it sharper",
      finalImageApiPrompt: "final image prompt",
    });
  });

  it("turns old flat candidate fields into a visible legacy API candidate", () => {
    const icon: AppStudioAiIconSuggestion = {
      candidatePngDataUrl: PNG_A,
      candidateUrl: "icon_candidate_1.png",
      promptInitial: "initial prompt",
      candidates: [],
    };

    const normalized = normalizeAppStudioIconProposal(icon);

    expect(normalized.apiCandidates).toHaveLength(1);
    expect(normalized.apiCandidates[0]).toMatchObject({
      candidateId: "icon_candidate_1",
      source: "legacy",
      fallback: false,
      pngDataUrl: PNG_A,
    });
  });

  it("normalizes legacy fallback source and reference-only quality markers", () => {
    const icon: AppStudioAiIconSuggestion = {
      candidates: [
        {
          candidateId: "legacy_quality",
          number: 1,
          source: "api_generate",
          fallback: false,
          scoreBasis: "prompt_concept_only",
          imageEvaluationStatus: "fallback_rule_based",
        },
      ],
    };

    const normalized = normalizeAppStudioIconProposal(icon, "fallback_png");

    expect(normalized.currentSource).toBe("default_icon");
    expect(normalizeIconSource("provisional_fallback_png")).toBe("default_icon");
    expect(iconSourceLabel("fallback_png")).toBe("ToolHub共通default icon");
    expect(iconSourceLabel("provisional_fallback_png")).toBe("ToolHub共通default icon");
    expect(normalized.apiCandidates[0].scoreBasis).toBe("rule_based_prompt_and_manifest");
    expect(normalized.apiCandidates[0].imageEvaluationStatus).toBe("deterministic_png_check");
  });

  it("does not treat default icon override data as an adoptable candidate preview", () => {
    const icon: AppStudioAiIconSuggestion = {
      finalPngDataUrl: PNG_DEFAULT,
      candidates: [],
    };

    expect(previewIconDataUrl({ selectedIconSource: "candidate_png", pngDataUrl: PNG_A }, { ok: true, metadata: EMPTY_METADATA, icon, warnings: [] })).toBe(PNG_A);
    expect(previewIconDataUrl({ selectedIconSource: "default_icon", pngDataUrl: PNG_B }, { ok: true, metadata: EMPTY_METADATA, icon, warnings: [] })).toBe(PNG_DEFAULT);
  });
});
