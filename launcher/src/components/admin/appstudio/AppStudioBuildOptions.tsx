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
    label: "requirements.lock生成",
    summary: "常にON",
    detail: "依存関係を固定し、ビルド再現性を高めます。依存がない場合も空または最小lockとして扱います。",
    icon: LockKeyhole,
  },
  {
    label: "frozen-folder build",
    summary: "常にON",
    detail: "Python不要で配布できるPyInstaller --onedir形式の実行フォルダを作成します。--onefileは標準にしません。",
    icon: PackageCheck,
  },
  {
    label: "配布物検証",
    summary: "常にON",
    detail: "exe、run.entry、同梱ファイル、禁止ファイル混入、build_env分離、サイズを確認します。",
    icon: ShieldCheck,
  },
  {
    label: "ビルド用環境",
    summary: "内部処理",
    detail: "exe作成のために一時的なbuild_envを使用します。利用者PCやruntime/app_envsには要求しません。",
    icon: Hammer,
  },
];

export function AppStudioBuildOptions({ request, onChange }: Props) {
  const fixedRequest: AppStudioImportRequest = {
    ...request,
    buildMode: "frozen-folder",
    createAppEnv: false,
    rebuildAppEnv: false,
    generateLock: true,
    buildFrozenFolder: true,
    verifyRuntime: true,
  };

  const needsNormalization =
    request.buildMode !== fixedRequest.buildMode ||
    request.createAppEnv ||
    request.rebuildAppEnv ||
    !request.generateLock ||
    !request.buildFrozenFolder ||
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
        <h4>配布用exeを作成して登録</h4>
      </div>

      <div className="studio-build-help">
        <strong>通常ユーザー向け配布に固定</strong>
        <p>Pythonソースを解析し、必要ファイルだけを同梱したfrozen-folderを作成して登録します。既存exe登録、Python直接実行、app_env実行方式は通常新規登録では選べません。</p>
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
