# Runtime Packaging

This document describes how ToolHub prepares shared runtime files for release. Runtime packaging is a release-readiness
task, not app cleanup. Runtime binaries are intentionally not committed to Git and are never downloaded automatically by
ToolHub scripts.

## Current App Studio Policy

Normal App Studio registration creates frozen-folder apps under `apps/<app_id>/`.

```text
Python source -> build_env -> PyInstaller frozen-folder -> apps/<app_id>/
```

For these normal apps:

- `apps/<app_id>/` is the app source of truth.
- `run.runner` is normally `exe`.
- `run.entry` points at `bin/<app_id>/<app_id>.exe`.
- `runtime/app_envs/<app_id>` is not required at runtime.
- `build_env` is a build-only environment and must not be copied into `runtime/`, App Packs, or `final_app`.

The `runtime/app_envs/` folder remains only for legacy compatibility and possible future app-env execution modes.

## Runtime Layout

```text
runtime/
|- README.md
|- runtime_manifest.example.json
|- python/
|- app_envs/
`- web_automation_runtime/
```

Tracked files are limited to docs, scripts, `.gitkeep`, and manifest examples. Large runtime artifacts are local release
inputs and remain ignored by Git.

## Preparing Runtime

Prepare placeholder folders and warnings when no approved archive is available:

```powershell
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
```

Prepare Python runtime from an internally approved archive:

```powershell
.\scripts\prepare_runtime.ps1 `
  -PythonArchive .\vendor\runtime\python-runtime.zip `
  -PythonSha256 <sha256>
```

Prepare Web automation runtime from an internally approved archive:

```powershell
.\scripts\prepare_runtime.ps1 `
  -WebRuntimeArchive .\vendor\runtime\web-automation-runtime.zip `
  -WebRuntimeSha256 <sha256>
```

Prepare both in one run:

```powershell
.\scripts\prepare_runtime.ps1 `
  -PythonArchive .\vendor\runtime\python-runtime.zip `
  -PythonSha256 <sha256> `
  -WebRuntimeArchive .\vendor\runtime\web-automation-runtime.zip `
  -WebRuntimeSha256 <sha256>
```

Operational flags:

- `-AllowMissingRuntime`: treat missing archives/runtime as warnings.
- `-SkipPython`: skip Python runtime checks and extraction.
- `-SkipWebRuntime`: skip Web runtime checks and extraction.
- `-CleanDestination`: clear the target runtime folder before extraction.
- `-DryRun`: preview writes/extraction without changing files.
- `-CreateAppEnvSkeletons`: create compatibility-only `runtime/app_envs/<app_id>/` skeletons.

`-SourceArchive` and `-SourceSha256` are retained as aliases for `-PythonArchive` and `-PythonSha256`.

## Safety Rules

`prepare_runtime.ps1` follows these safety rules:

- It never downloads runtime files from the internet.
- It expands only explicitly provided local archives.
- It verifies SHA256 before extraction when a hash is provided.
- A SHA256 mismatch stops extraction.
- Python archives extract only to `runtime/python/`.
- Web runtime archives extract only to `runtime/web_automation_runtime/`.
- Archive path traversal is rejected before files are written.
- Runtime binaries remain ignored by Git.

## Runtime Verification

Use read-only verification:

```powershell
.\scripts\verify_runtime.ps1
.\scripts\verify_runtime.ps1 -Json
```

Normal mode reports missing runtime as warnings so local development can continue. Strict runtime verification fails
until shared runtime files are present:

```powershell
.\scripts\verify_runtime.ps1 -RequireRuntime
```

The verifier checks:

- `runtime/python/python.exe`
- `python.exe --version`
- a minimal Python stdlib import check when Python exists
- non-placeholder files in `runtime/web_automation_runtime/`
- whether app_env directories are missing, skeleton-only, or present with files

Missing `runtime/app_envs/<app_id>` is informational for normal frozen-folder apps and is not a runtime packaging
failure.

## Runtime Manifest Example

`runtime/runtime_manifest.example.json` documents the intended local runtime state. It is an example, not a generated
authoritative manifest. Runtime binaries and local runtime archive manifests remain outside Git unless a separate
release policy explicitly approves them.

## Release Readiness Relation

Runtime warnings are tracked by:

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\verify_release.ps1
```

Current warning categories:

- `runtime_packaging_required`: shared Python or Web runtime is missing.
- `docs_check_adjustment_candidates`: strict app_env policy still needs a decision for frozen-folder apps.
- `intentional_warnings`: hidden apps with source or missing app_env folders that are not deletion candidates.

These warnings must not be resolved by deleting apps.

## Git Policy

Commit:

- `runtime/README.md`
- `runtime/**/.gitkeep`
- `runtime/runtime_manifest.example.json`
- runtime preparation and verification scripts
- runtime docs

Do not commit:

- `runtime/python/*` runtime binaries
- `runtime/app_envs/*` runtime environment contents
- `runtime/web_automation_runtime/*` runtime binaries
- `vendor/runtime/`
- `tools/runtime_sources/`

This policy is enforced by `.gitignore`.
