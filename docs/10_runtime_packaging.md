# Runtime Packaging

This document describes how ToolHub prepares shared runtime files for local execution and release checks. Runtime binaries and created virtual environments are local artifacts; they are not committed to Git and are never downloaded automatically by ToolHub scripts.

## Current App Studio Policy

Normal App Studio registration uses a shared versioned runtime:

```text
Python source -> requirements.lock -> runtime/envs/<env_id> -> apps/<app_id>/
```

For normal shared-env apps:

- `apps/<app_id>/` remains the app source of truth.
- `run.runner` is `python_shared_env`.
- `run.entry` points at the copied source under `src/`.
- `run.env_id` selects `runtime/envs/<env_id>`.
- `runtime.required_runtime` is `python-shared-env:<env_id>`.
- `requirements.lock` is required and included in `apps/<app_id>/` and App Pack zip.
- `runtime/app_envs/<app_id>` is not required at runtime.

The old `runtime/app_envs/` folder remains only for legacy compatibility and explicit app-env execution modes. Existing `run.runner: exe` frozen-folder apps remain supported for compatibility, but they are no longer the normal new-registration path.

## Runtime Layout

```text
runtime/
|- README.md
|- runtime_manifest.example.json
|- python/
|- envs/
|- app_envs/
`- web_automation_runtime/
```

Tracked files are limited to docs, scripts, `.gitkeep`, and manifest examples. Large runtime artifacts are local release inputs and remain ignored by Git.

## Preparing Runtime

Prepare placeholder folders and warnings when no approved archive is available:

```powershell
.\scripts\prepare_runtime.ps1 -AllowMissingRuntime
```

App Studio creates `runtime/envs/<env_id>` during registration when it encounters a dependency lock that does not already have a shared environment. `prepare_runtime.ps1` only prepares the runtime folder structure and optional base runtime archives.

Operational flags:

- `-AllowMissingRuntime`: treat missing archives/runtime as warnings.
- `-SkipPython`: skip Python runtime checks and extraction.
- `-SkipWebRuntime`: skip Web runtime checks and extraction.
- `-CleanDestination`: clear the target runtime folder before extraction.
- `-DryRun`: preview writes/extraction without changing files.
- `-CreateAppEnvSkeletons`: create compatibility-only `runtime/app_envs/<app_id>/` skeletons.

## Runtime Verification

Use read-only verification:

```powershell
.\scripts\verify_runtime.ps1
.\scripts\verify_runtime.ps1 -Json
```

The verifier checks:

- `runtime/python/python.exe`, when a bundled Python runtime is expected.
- `python.exe --version` and a minimal stdlib import check when Python exists.
- non-placeholder files in `runtime/web_automation_runtime/`.
- whether any versioned shared environments exist under `runtime/envs/`.
- whether legacy `runtime/app_envs/<app_id>` directories are present or missing.

Missing `runtime/app_envs/<app_id>` is informational for normal shared-env apps and is not a runtime packaging failure.

## Release Checks

`verify_release.ps1` checks `python-shared-env:<env_id>` apps against `runtime/envs/<env_id>/Scripts/python.exe` instead of requiring `runtime/app_envs/<app_id>`. App Pack validation still checks `app.yaml`, `README.md`, `requirements.txt`, `requirements.lock`, `display.icon`, and `run.entry`.

These commands are relevant:

```powershell
.\scripts\report_release_readiness.ps1
.\scripts\verify_release.ps1
```

Warnings about missing runtime files must not be resolved by deleting apps. Fix the runtime artifact, App Pack, or manifest contract that the warning identifies.

## Git Policy

Commit:

- `runtime/README.md`
- `runtime/**/.gitkeep`
- `runtime/runtime_manifest.example.json`
- runtime preparation and verification scripts
- runtime docs

Do not commit:

- `runtime/python/*` runtime binaries
- `runtime/envs/*` virtual environment contents
- `runtime/app_envs/*` runtime environment contents
