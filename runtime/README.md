# ToolHub Runtime

This directory is prepared by `scripts/prepare_runtime.ps1`.

Planned release layout:

```text
runtime/
|- python/
|- app_envs/
`- web_automation_runtime/
```

Large runtime artifacts are intentionally not tracked in Git. Place local runtime archives under `vendor/runtime/` or `tools/runtime_sources/` and pass them to `prepare_runtime.ps1 -SourceArchive <path>`.

Default behavior does not download anything from the internet.
