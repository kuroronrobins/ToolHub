# Execution Test Report

- app_id: `test`
- generated_at: `2026-04-26T17:50:58`
- overall_status: `warn`
- approval_allowed: `true`

| Status | Check | Detail |
| --- | --- | --- |
| pass | app.yaml exists | C:\Users\kuroron\Documents\RD\20260426_Toolhub\apps\test\app.yaml |
| pass | app.yaml parse | runner=python_app_env, entry=src/main.py |
| pass | runner supported | python_app_env |
| pass | run.entry exists | C:\Users\kuroron\Documents\RD\20260426_Toolhub\apps\test\src\main.py |
| pass | secret scan | No high severity secret findings. |
| warn | python runtime | Missing C:\Users\kuroron\Documents\RD\20260426_Toolhub\runtime\app_envs\test\Scripts\python.exe and C:\Users\kuroron\Documents\RD\20260426_Toolhub\runtime\python\python.exe. StrictApproval will reject this. |
| warn | runner dry execution | Skipped because ToolHub Python runtime/app_env is not present. |

Human approval is required before enabling this app in release/app_manifest.json.
