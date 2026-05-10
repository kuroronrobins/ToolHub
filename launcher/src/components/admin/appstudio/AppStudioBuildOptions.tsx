import { useEffect } from "react";
import { Hammer, LockKeyhole, PackageCheck, ShieldCheck } from "lucide-react";
import type { AppStudioImportRequest } from "../../../lib/appStudioTypes";

interface Props {
  request: AppStudioImportRequest;
  onChange: (next: AppStudioImportRequest) => void;
}

interface FixedPolicyInfo {
  label: string;
  summary: string;
  detail: string;
  icon: typeof LockKeyhole;
}

const FIXED_POLICIES: FixedPolicyInfo[] = [
  {
    label: "requirements.lock",
    summary: "常に作成",
    detail: "登録元で動作している依存バージョンを優先して固定し、同じ lock のアプリは共通環境を再利用します。",
    icon: LockKeyhole,
  },
  {
    label: "共有ランタイム",
    summary: "常に使用",
    detail: "アプリごとに環境を複製せず、Python と依存バージョン単位の runtime/envs を作成または再利用します。",
    icon: PackageCheck,
  },
  {
    label: "起動検証",
    summary: "常に実行",
    detail: "run.entry、app.yaml、requirements.lock、共有環境、短時間起動時の致命的エラーを確認します。",
    icon: ShieldCheck,
  },
  {
    label: "配布サイズ",
    summary: "重複を抑制",
    detail: "Playwright や Flet など重い依存はバージョン別の共通環境へ集約し、アプリ本体にはソースと設定を登録します。",
    icon: Hammer,
  },
];

export function AppStudioBuildOptions({ request, onChange }: Props) {
  const fixedRequest: AppStudioImportRequest = {
    ...request,
    buildMode: "shared-env",
    createAppEnv: false,
    rebuildAppEnv: false,
    generateLock: true,
    buildFrozenFolder: false,
    verifyRuntime: true,
  };

  const needsNormalization =
    request.buildMode !== fixedRequest.buildMode ||
    request.createAppEnv ||
    request.rebuildAppEnv ||
    !request.generateLock ||
    request.buildFrozenFolder ||
    !request.verifyRuntime;

  useEffect(() => {
    if (needsNormalization) {
      onChange(fixedRequest);
    }
  }, [fixedRequest, needsNormalization, onChange]);

  return (
    <section className="studio-step studio-build-options">
      <div>
        <span className="studio-step-index">B</span>
        <h4>共有ランタイムで登録</h4>
      </div>

      <div className="studio-build-help">
        <strong>通常登録は共有ランタイム方式に固定</strong>
        <p>Pythonソースを解析し、動作済みの依存バージョンを lock して共通環境へ登録します。既存exe登録、Python直接実行、app_env実行方式は通常新規登録では選べません。</p>
      </div>

      <div className="studio-option-grid fixed-policy-grid">
        {FIXED_POLICIES.map((policy) => {
          const Icon = policy.icon;
          return (
            <div className="studio-option-card fixed" key={policy.label}>
              <span className="studio-option-icon" aria-hidden="true">
                <Icon size={17} />
              </span>
              <span className="studio-option-text">
                <span className="studio-option-title">
                  <strong>{policy.label}</strong>
                  <em>{policy.summary}</em>
                </span>
                <small>{policy.detail}</small>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
