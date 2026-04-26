# Approval Record

- status: `approved`
- recorded_at: `2026-04-26T17:51:10`
- app_id: `test`
- version: `0.1.0`
- enabled: `True`
- package: `C:\Users\kuroron\Documents\RD\20260426_Toolhub\release\app_packs\test-0.1.0.zip`

## Failures


## execution_test_result.json

```json
{
  "app_id": "test",
  "generated_at": "2026-04-26T17:50:58",
  "overall_status": "warn",
  "approval_allowed": true,
  "checks": [
    {
      "name": "app.yaml exists",
      "status": "pass",
      "detail": "C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\apps\\test\\app.yaml"
    },
    {
      "name": "app.yaml parse",
      "status": "pass",
      "detail": "runner=python_app_env, entry=src/main.py"
    },
    {
      "name": "runner supported",
      "status": "pass",
      "detail": "python_app_env"
    },
    {
      "name": "run.entry exists",
      "status": "pass",
      "detail": "C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\apps\\test\\src\\main.py"
    },
    {
      "name": "secret scan",
      "status": "pass",
      "detail": "No high severity secret findings."
    },
    {
      "name": "python runtime",
      "status": "warn",
      "detail": "Missing C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runtime\\app_envs\\test\\Scripts\\python.exe and C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runtime\\python\\python.exe. StrictApproval will reject this."
    },
    {
      "name": "runner dry execution",
      "status": "warn",
      "detail": "Skipped because ToolHub Python runtime/app_env is not present."
    }
  ]
}
```

## verify_release.ps1

```json
{
  "status": "ok",
  "exit_code": 0,
  "stdout": "[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\release\\manifest.json exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\release\\app_manifest.json exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runner exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\apps exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runtime exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runtime\\app_envs exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runtime\\web_automation_runtime exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\config.default exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\updater exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\installer exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\release\\staging exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\release\\dist_installer exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\release\\app_packs exists\n[OK] C:\\Users\\kuroron\\Documents\\RD\\20260426_Toolhub\\runtime\\README.md exists\n[WARN] Python runtime executable is not bundled yet\n[WARN] Web automation runtime files are not bundled yet\n[OK] manifest schema_version is 1\n[OK] apps_manifest points to app_manifest.json\n[OK] installer file exists\n[OK] installer sha256 matches\n[OK] installer size matches\n[OK] installer type is set\n[OK] app_manifest schema_version is 1\n[OK] sample_gui_app app.yaml exists\n[OK] sample_gui_app version is set\n[OK] sample_gui_app required_core is set\n[OK] sample_gui_app required_runner is set\n[OK] sample_gui_app app_env skeleton exists\n[OK] sample_gui_app app pack exists\n[OK] sample_gui_app app pack sha256 matches\n[OK] sample_gui_app app pack contains app.yaml\n[OK] sample_gui_app app pack contains pack_manifest.json\n[OK] sample_cli_app app.yaml exists\n[OK] sample_cli_app version is set\n[OK] sample_cli_app required_core is set\n[OK] sample_cli_app required_runner is set\n[OK] sample_cli_app app_env skeleton exists\n[OK] sample_cli_app app pack exists\n[OK] sample_cli_app app pack sha256 matches\n[OK] sample_cli_app app pack contains app.yaml\n[OK] sample_cli_app app pack contains pack_manifest.json\n[OK] sample_playwright_app app.yaml exists\n[OK] sample_playwright_app version is set\n[OK] sample_playwright_app required_core is set\n[OK] sample_playwright_app required_runner is set\n[OK] sample_playwright_app app_env skeleton exists\n[OK] sample_playwright_app app pack exists\n[OK] sample_playwright_app app pack sha256 matches\n[OK] sample_playwright_app app pack contains app.yaml\n[OK] sample_playwright_app app pack contains pack_manifest.json\n[OK] app_20251123_excelbatchreplace app.yaml exists\n[OK] app_20251123_excelbatchreplace version is set\n[OK] app_20251123_excelbatchreplace required_core is set\n[OK] app_20251123_excelbatchreplace required_runner is set\n[WARN] app_20251123_excelbatchreplace app_env skeleton is missing\n[OK] app_20251123_excelbatchreplace app pack exists\n[OK] app_20251123_excelbatchreplace app pack sha256 matches\n[OK] app_20251123_excelbatchreplace app pack contains app.yaml\n[OK] app_20251123_excelbatchreplace app pack contains pack_manifest.json\n[OK] test app.yaml exists\n[OK] test version is set\n[OK] test required_core is set\n[OK] test required_runner is set\n[WARN] test app_env skeleton is missing\n[OK] test app pack exists\n[OK] test app pack sha256 matches\n[OK] test app pack contains app.yaml\n[OK] test app pack contains pack_manifest.json\n[OK] installer staging manifest exists\n",
  "stderr": ""
}
```
