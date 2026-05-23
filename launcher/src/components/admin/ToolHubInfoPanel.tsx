import { Info, PackageCheck, Route } from "lucide-react";

export function ToolHubInfoPanel() {
  return (
    <section className="admin-panel-section">
      <div className="admin-section-head">
        <div>
          <p className="dialog-kicker">ToolHub情報</p>
          <h3>バージョンと製品情報</h3>
        </div>
        <span className="admin-status-pill">0.1.0</span>
      </div>

      <div className="admin-info-list">
        <div>
          <Info size={20} aria-hidden="true" />
          <div>
            <strong>概要</strong>
            <p>業務アプリを探して起動するためのデスクトップランチャーです。</p>
          </div>
        </div>
        <div>
          <Route size={20} aria-hidden="true" />
          <div>
            <strong>責務分担</strong>
            <p>launcherは表示とdesktop shell、runnerはPythonアプリ起動、appsは登録アプリ情報を担当します。</p>
          </div>
        </div>
        <div>
          <PackageCheck size={20} aria-hidden="true" />
          <div>
            <strong>配布方針</strong>
            <p>利用者にはインストーラー型で配布し、PythonやNode.jsなどの開発環境を手動導入させない方針です。</p>
          </div>
        </div>
      </div>

      <details className="admin-details" open>
        <summary>構成バージョン</summary>
        <dl>
          <div>
            <dt>Core</dt>
            <dd>0.1.0</dd>
          </div>
          <div>
            <dt>Runner</dt>
            <dd>0.1.0</dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
