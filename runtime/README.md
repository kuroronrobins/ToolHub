# ToolHub Runtime

This directory is prepared by `scripts/prepare_runtime.ps1`.

Planned release layout:

```text
runtime/
|- python/
|- app_envs/
`- web_automation_runtime/
```

Large runtime artifacts are intentionally not tracked in Git. Place approved local runtime archives under
`vendor/runtime/`, `tools/runtime_sources/`, or another internal location and pass them explicitly:

```powershell
.\scripts\prepare_runtime.ps1 -PythonArchive <python.zip> -PythonSha256 <sha256>
.\scripts\prepare_runtime.ps1 -WebRuntimeArchive <web-runtime.zip> -WebRuntimeSha256 <sha256>
```

Default behavior does not download anything from the internet. Normal frozen-folder apps do not require
`runtime/app_envs/<app_id>`; create compatibility skeletons only with `-CreateAppEnvSkeletons`.
