# ToolHub Documentation Guide

このフォルダは、ToolHub の設計、運用、配布、検証に関する文書を置く場所です。

Codex の初動では [00_AI_CONTEXT.md](00_AI_CONTEXT.md) を優先します。詳細が必要な場合だけ、下の表から目的に合う文書を読んでください。

## まず読むもの

通常の作業では、次の順に読むと迷いにくいです。

1. [00_AI_CONTEXT.md](00_AI_CONTEXT.md): Codex 用の現在前提。
2. [../README.md](../README.md): 起動方法、配布方針、検証コマンドの入口。
3. [01_architecture.md](01_architecture.md): launcher、runner、apps、scripts、release/runtime の責務分担。
4. [13_app_studio.md](13_app_studio.md): 現行 App Studio 登録フロー。
5. [06_acceptance_checklist.md](06_acceptance_checklist.md): リリースや検収で見る項目。

## 現行仕様の入口

| 目的 | 読む文書 |
| --- | --- |
| Codex 用の現在前提を見る | [00_AI_CONTEXT.md](00_AI_CONTEXT.md) |
| 全体像を確認する | [00_concept.md](00_concept.md), [01_architecture.md](01_architecture.md) |
| `app.yaml` の仕様を見る | [02_app_manifest_spec.md](02_app_manifest_spec.md) |
| 手動で簡単な app を追加する | [03_add_new_app.md](03_add_new_app.md) |
| Web 自動化 app の扱いを見る | [04_playwright_app_rule.md](04_playwright_app_rule.md) |
| App Studio の現在仕様を見る | [13_app_studio.md](13_app_studio.md) |
| 管理者画面、AI/API キー、アイコン設定を見る | [14_admin_and_ai_settings.md](14_admin_and_ai_settings.md) |
| 既存 app 更新 GUI MVP を見る | [15_app_studio_update_gui.md](15_app_studio_update_gui.md) |
| legacy frozen-folder / exe 互換を確認する | [16_app_studio_exe_build_operations.md](16_app_studio_exe_build_operations.md) |
| app 管理と削除安全性を見る | [17_app_management_model.md](17_app_management_model.md), [18_app_delete_execution_plan.md](18_app_delete_execution_plan.md), [19_full_delete_executor_design.md](19_full_delete_executor_design.md) |

## 配布と検証

| 目的 | 読む文書 |
| --- | --- |
| build / release 手順 | [05_build_and_release.md](05_build_and_release.md) |
| 検収 checklist | [06_acceptance_checklist.md](06_acceptance_checklist.md) |
| installer 配布方針 | [07_installer_distribution.md](07_installer_distribution.md) |
| 更新設計 | [08_update_design.md](08_update_design.md) |
| App Pack 仕様 | [09_app_pack_spec.md](09_app_pack_spec.md) |
| runtime packaging | [10_runtime_packaging.md](10_runtime_packaging.md) |
| Windows build 環境 | [11_build_environment.md](11_build_environment.md) |
| トラブルシュート | [12_troubleshooting.md](12_troubleshooting.md) |
| release readiness の分類 | [20_release_readiness_cleanup.md](20_release_readiness_cleanup.md) |
| Beta installer / updater の履歴と現在の残作業 | [22_beta_installer_updater_plan.md](22_beta_installer_updater_plan.md) |
| GitHub Releases を使った更新配布の実装方針 | [35_github_release_updater_implementation_plan.md](35_github_release_updater_implementation_plan.md) |
| ワンクリック公開と更新内容表示の実装方針 | [36_one_click_release_cockpit_plan.md](36_one_click_release_cockpit_plan.md) |
| VirtualBox で現行有効アプリ入り installer を検証する | [34_virtualbox_two_app_validation_plan.md](34_virtualbox_two_app_validation_plan.md) |

## 検証プロトコル

| 文書 | 位置づけ |
| --- | --- |
| [29_app_registration_zero_stress_validation_protocol.md](29_app_registration_zero_stress_validation_protocol.md) | App Studio が「main.py 指定だけ」で登録できるかを検証する protocol。 |

## Archive の扱い

[archive/](archive/) は過去資料の入口です。完了済みの調査記録、古い実装計画、検証 evidence、役目を終えた handoff は現在仕様ではないため、通常の作業開始時には読みません。過去経緯が必要な場合だけ確認してください。
