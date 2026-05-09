import { previewIconDataUrl } from "../../../lib/appStudioIconProposal";
import type { AppStudioAiProposal, AppStudioEditableMetadata, AppStudioIconOverride } from "../../../lib/appStudioTypes";

interface Props {
  appId?: string;
  name?: string;
  metadata?: AppStudioEditableMetadata;
  proposal?: AppStudioAiProposal | null;
  iconOverride?: AppStudioIconOverride;
}

export function AppStudioLauncherPreview({ appId, name, metadata, proposal, iconOverride }: Props) {
  const iconDataUrl = previewIconDataUrl(iconOverride, proposal);
  const categories = metadata?.categories?.filter(Boolean).slice(0, 3) ?? [];
  return (
    <section className="studio-launcher-preview" aria-label="ランチャーカードプレビュー">
      <div className="studio-preview-icon" aria-hidden="true">
        {iconDataUrl ? <img src={iconDataUrl} alt="" /> : <span>{previewInitial(name, appId)}</span>}
      </div>
      <div className="studio-preview-body">
        <p className="dialog-kicker">ランチャー表示プレビュー</p>
        <h4>{name?.trim() || "表示名を入力してください"}</h4>
        <p>{metadata?.shortDescription?.trim() || "一言説明は未入力です。"}</p>
        <div className="studio-preview-tags">
          {categories.length ? categories.map((category) => <span key={category}>{category}</span>) : <span>カテゴリ未設定</span>}
        </div>
      </div>
    </section>
  );
}

function previewInitial(name?: string, appId?: string): string {
  const source = name?.trim() || appId?.trim() || "A";
  return source.slice(0, 1).toUpperCase();
}
