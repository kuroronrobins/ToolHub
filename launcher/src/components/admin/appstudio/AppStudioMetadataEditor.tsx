import { useMemo, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import {
  cleanList,
  cleanString,
  createEmptyAppStudioMetadata,
  hasEditableMetadata,
  metadataFromSuggestion,
} from "../../../lib/appStudioMetadata";
import type { AppStudioAiMetadataSuggestion, AppStudioEditableMetadata } from "../../../lib/appStudioTypes";
import { AppStudioArrayField } from "./AppStudioArrayField";
import { AppStudioMetadataField } from "./AppStudioMetadataField";

type ScalarKey = "shortDescription" | "description" | "changeSummary";
type ArrayKey = "categories" | "keywords" | "examples" | "useCases" | "inputs" | "outputs" | "notes" | "releaseNotes";
type MetadataKey = ScalarKey | ArrayKey;
type FieldHistory = Partial<Record<MetadataKey, string | string[]>>;

const SCALAR_FIELDS: Array<{ key: ScalarKey; label: string; rows: number; releaseOnly?: boolean }> = [
  { key: "shortDescription", label: "short_description", rows: 2 },
  { key: "description", label: "description", rows: 4 },
  { key: "changeSummary", label: "change_summary", rows: 3, releaseOnly: true },
];

const ARRAY_FIELDS: Array<{ key: ArrayKey; label: string; releaseOnly?: boolean }> = [
  { key: "categories", label: "categories" },
  { key: "keywords", label: "keywords" },
  { key: "examples", label: "examples" },
  { key: "useCases", label: "use_cases" },
  { key: "inputs", label: "inputs" },
  { key: "outputs", label: "outputs" },
  { key: "notes", label: "notes" },
  { key: "releaseNotes", label: "release_notes", releaseOnly: true },
];

interface Props {
  metadata?: AppStudioEditableMetadata;
  proposal?: AppStudioAiMetadataSuggestion | null;
  includeReleaseFields?: boolean;
  onChange: (metadata: AppStudioEditableMetadata) => void;
}

export function AppStudioMetadataEditor({ metadata, proposal, includeReleaseFields = false, onChange }: Props) {
  const [history, setHistory] = useState<FieldHistory>({});
  const current = metadata ?? createEmptyAppStudioMetadata();
  const proposalMetadata = useMemo(() => (proposal ? metadataFromSuggestion(proposal) : null), [proposal]);
  const scalarFields = SCALAR_FIELDS.filter((field) => includeReleaseFields || !field.releaseOnly);
  const arrayFields = ARRAY_FIELDS.filter((field) => includeReleaseFields || !field.releaseOnly);
  const hasProposal = hasEditableMetadata(proposalMetadata ?? undefined);

  function update(partial: Partial<AppStudioEditableMetadata>) {
    onChange({ ...current, ...partial });
  }

  function adoptScalar(key: ScalarKey) {
    const value = cleanString(proposalMetadata?.[key]);
    if (!value) {
      return;
    }
    setHistory((existing) => ({ ...existing, [key]: current[key] ?? "" }));
    update({ [key]: value });
  }

  function adoptArray(key: ArrayKey) {
    const value = cleanList(proposalMetadata?.[key]);
    if (!value.length) {
      return;
    }
    setHistory((existing) => ({ ...existing, [key]: cleanList(current[key]) }));
    update({ [key]: value });
  }

  function revertScalar(key: ScalarKey) {
    const value = history[key];
    if (typeof value !== "string") {
      return;
    }
    setHistory((existing) => withoutKey(existing, key));
    update({ [key]: value });
  }

  function revertArray(key: ArrayKey) {
    const value = history[key];
    if (!Array.isArray(value)) {
      return;
    }
    setHistory((existing) => withoutKey(existing, key));
    update({ [key]: value });
  }

  function adoptAll() {
    if (!proposalMetadata) {
      return;
    }
    const next: AppStudioEditableMetadata = { ...current };
    const nextHistory: FieldHistory = { ...history };
    for (const field of scalarFields) {
      const value = cleanString(proposalMetadata[field.key]);
      if (value) {
        nextHistory[field.key] = current[field.key] ?? "";
        next[field.key] = value;
      }
    }
    for (const field of arrayFields) {
      const value = cleanList(proposalMetadata[field.key]);
      if (value.length) {
        nextHistory[field.key] = cleanList(current[field.key]);
        next[field.key] = value;
      }
    }
    setHistory(nextHistory);
    onChange(next);
  }

  return (
    <section className="studio-step">
      <div>
        <span className="studio-step-index">M</span>
        <h4>Metadata</h4>
      </div>
      <div className="studio-action-row">
        <button className="secondary-button" type="button" onClick={adoptAll} disabled={!hasProposal}>
          <CheckCircle2 size={17} aria-hidden="true" />
          Adopt all proposals
        </button>
      </div>
      <div className="studio-metadata-grid">
        {scalarFields.map((field) => (
          <AppStudioMetadataField
            key={field.key}
            label={field.label}
            rows={field.rows}
            value={current[field.key] ?? ""}
            proposal={proposalMetadata?.[field.key] ?? ""}
            status={statusForString(current[field.key], proposalMetadata?.[field.key])}
            warning={warningForString(field.key, current[field.key])}
            canRevert={typeof history[field.key] === "string"}
            onChange={(value) => update({ [field.key]: value })}
            onAdopt={() => adoptScalar(field.key)}
            onRevert={() => revertScalar(field.key)}
          />
        ))}
        {arrayFields.map((field) => (
          <AppStudioArrayField
            key={field.key}
            label={field.label}
            value={current[field.key]}
            proposal={proposalMetadata?.[field.key]}
            status={statusForList(current[field.key], proposalMetadata?.[field.key])}
            warning={warningForList(field.key, current[field.key])}
            canRevert={Array.isArray(history[field.key])}
            onChange={(value) => update({ [field.key]: value })}
            onAdopt={() => adoptArray(field.key)}
            onRevert={() => revertArray(field.key)}
          />
        ))}
      </div>
    </section>
  );
}

function withoutKey(history: FieldHistory, key: MetadataKey): FieldHistory {
  const next = { ...history };
  delete next[key];
  return next;
}

function statusForString(current?: string, proposal?: string | null): string {
  const currentValue = cleanString(current);
  const proposalValue = cleanString(proposal);
  if (!proposalValue) {
    return "no proposal";
  }
  if (!currentValue) {
    return "empty";
  }
  return currentValue === proposalValue ? "adopted" : "diff";
}

function statusForList(current?: string[], proposal?: string[]): string {
  const currentValue = cleanList(current);
  const proposalValue = cleanList(proposal);
  if (!proposalValue.length) {
    return "no proposal";
  }
  if (!currentValue.length) {
    return "empty";
  }
  return sameList(currentValue, proposalValue) ? "adopted" : "diff";
}

function warningForString(key: ScalarKey, value?: string): string {
  const cleaned = cleanString(value);
  if (!cleaned && (key === "shortDescription" || key === "description")) {
    return `${key === "shortDescription" ? "short_description" : key} is empty; CLI fallback will be used unless you adopt or edit it.`;
  }
  if (key === "shortDescription" && cleaned.length > 160) {
    return "short_description is long for launcher cards.";
  }
  return "";
}

function warningForList(key: ArrayKey, value?: string[]): string {
  const cleaned = cleanList(value);
  if (!cleaned.length && (key === "categories" || key === "keywords")) {
    return `${key} is empty; CLI fallback will be used unless you adopt or edit it.`;
  }
  return "";
}

function sameList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((item, index) => item === right[index]);
}
