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

type ScalarKey = "shortDescription" | "description" | "primaryCategory" | "changeSummary";
type ArrayKey = "targetCategories" | "tags" | "categories" | "keywords" | "examples" | "useCases" | "inputs" | "outputs" | "notes" | "releaseNotes";
type MetadataKey = ScalarKey | ArrayKey;
type FieldHistory = Partial<Record<MetadataKey, string | string[]>>;

const SCALAR_FIELDS: Array<{ key: ScalarKey; label: string; rows: number; releaseOnly?: boolean; detail?: boolean }> = [
  { key: "shortDescription", label: "一言説明", rows: 2 },
  { key: "description", label: "詳細説明", rows: 4 },
  { key: "primaryCategory", label: "補助分類", rows: 1 },
  { key: "changeSummary", label: "変更概要", rows: 3, releaseOnly: true },
];

const ARRAY_FIELDS: Array<{ key: ArrayKey; label: string; releaseOnly?: boolean; detail?: boolean }> = [
  { key: "targetCategories", label: "対象カテゴリ（先頭が表示カテゴリ）" },
  { key: "tags", label: "特徴タグ" },
  { key: "categories", label: "互換カテゴリ", detail: true },
  { key: "keywords", label: "検索キーワード" },
  { key: "examples", label: "利用例", detail: true },
  { key: "useCases", label: "用途", detail: true },
  { key: "inputs", label: "入力", detail: true },
  { key: "outputs", label: "出力", detail: true },
  { key: "notes", label: "備考", detail: true },
  { key: "releaseNotes", label: "リリースノート", releaseOnly: true, detail: true },
];

interface Props {
  metadata?: AppStudioEditableMetadata;
  proposal?: AppStudioAiMetadataSuggestion | null;
  includeReleaseFields?: boolean;
  compact?: boolean;
  onChange: (metadata: AppStudioEditableMetadata) => void;
}

export function AppStudioMetadataEditor({ metadata, proposal, includeReleaseFields = false, compact = false, onChange }: Props) {
  const [history, setHistory] = useState<FieldHistory>({});
  const current = metadata ?? createEmptyAppStudioMetadata();
  const proposalMetadata = useMemo(() => (proposal ? metadataFromSuggestion(proposal) : null), [proposal]);
  const scalarFields = SCALAR_FIELDS.filter((field) => includeReleaseFields || !field.releaseOnly);
  const arrayFields = ARRAY_FIELDS.filter((field) => includeReleaseFields || !field.releaseOnly);
  const primaryScalarFields = compact ? scalarFields.filter((field) => !field.detail && field.key !== "changeSummary") : scalarFields;
  const primaryArrayFields = compact ? arrayFields.filter((field) => !field.detail) : arrayFields;
  const detailScalarFields = compact ? scalarFields.filter((field) => field.detail || field.key === "changeSummary") : [];
  const detailArrayFields = compact ? arrayFields.filter((field) => field.detail) : [];
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
        <h4>登録情報</h4>
      </div>
      <div className="studio-action-row">
        <button className="secondary-button" type="button" onClick={adoptAll} disabled={!hasProposal}>
          <CheckCircle2 size={17} aria-hidden="true" />
          AI提案をすべて採用
        </button>
      </div>
      <div className="studio-metadata-grid">
        {renderScalarFields(primaryScalarFields)}
        {renderArrayFields(primaryArrayFields)}
        {compact && (detailScalarFields.length || detailArrayFields.length) ? (
          <details className="studio-collapsible">
            <summary>
              <span>詳細項目を開く</span>
              <small>利用例、用途、入力、出力、備考を編集します。</small>
            </summary>
            <div className="studio-collapsible-body studio-metadata-grid">
              {renderScalarFields(detailScalarFields)}
              {renderArrayFields(detailArrayFields)}
            </div>
          </details>
        ) : null}
      </div>
    </section>
  );

  function renderScalarFields(fields: typeof scalarFields) {
    return fields.map((field) => (
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
    ));
  }

  function renderArrayFields(fields: typeof arrayFields) {
    return fields.map((field) => (
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
    ));
  }
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
  if (!cleaned && (key === "shortDescription" || key === "description" || key === "primaryCategory")) {
    const label = key === "shortDescription" ? "一言説明" : key === "description" ? "詳細説明" : "補助分類";
    return `${label}が未入力です。採用または手入力しない場合はCLI側のフォールバックが使われます。`;
  }
  if (key === "shortDescription" && cleaned.length > 160) {
    return "一言説明が長めです。ランチャーカードでは短い文の方が読みやすくなります。";
  }
  return "";
}

function warningForList(key: ArrayKey, value?: string[]): string {
  const cleaned = cleanList(value);
  if (!cleaned.length && (key === "targetCategories" || key === "keywords")) {
    return `${key === "targetCategories" ? "対象カテゴリ" : "検索キーワード"}が未入力です。採用または手入力しない場合はCLI側のフォールバックが使われます。`;
  }
  return "";
}

function sameList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((item, index) => item === right[index]);
}
