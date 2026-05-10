# Shared Versioned Runtime Plan

## Purpose

App Studio registration should prioritize "apps that already run directly can also run after ToolHub registration".

The current normal registration flow builds a PyInstaller frozen-folder for every app. That has good distribution
properties, but it can break apps when App Studio resolves broad requirements such as `flet>=0.23.2` to a newer library
version than the one used by the working direct-run environment.

This plan changes the long-term direction to a shared versioned runtime model:

- Apps do not each keep a full private virtual environment.
- Apps do not all share one global latest environment.
- ToolHub creates and reuses runtime environments by dependency version set.
- If a newly registered app needs a version set that does not exist yet, ToolHub creates a new shared runtime for that
  version set.

The goal is to keep compatibility, startup speed, and total disk size in balance.

## Current Failure Pattern

The observed Flet app runs directly with:

```text
flet==0.28.3
flet-desktop==0.28.3
```

The same app was registered through App Studio with:

```text
flet==0.85.0
flet-desktop==0.85.0
```

The source uses `TextField(helper_text=...)`, which is accepted by the working direct-run Flet version but not by the
newer registered version. The registration process changed the runtime contract even though the source app itself was
usable.

The root problem is not only insufficient testing. The registration process must preserve or intentionally recreate the
known-good dependency versions.

## Design Decision

Adopt shared versioned runtimes as the standard direction for registered Python apps.

The runtime unit is an environment identified by Python version and locked dependency set, not by app id.

Example layout:

```text
runtime/
  python/
    3.13.2/
      python.exe
  envs/
    py313-flet0283-pypdf670-pymupdf1271/
      Scripts/python.exe
      Lib/site-packages/...
      toolhub_env_manifest.json
      requirements.lock
    py313-flet0850-pypdf6110-pymupdf1272/
      ...
  shared/
    playwright/
      1.46.0/
        chromium/...
      1.52.0/
        chromium/...
```

App manifests reference the selected runtime environment:

```yaml
run:
  runner: python_shared_env
  entry: app.py
  mode: gui
  env_id: py313-flet0283-pypdf670-pymupdf1271
runtime:
  requirements_lock: requirements.lock
  shared_env:
    env_id: py313-flet0283-pypdf670-pymupdf1271
    python: "3.13.2"
```

This should be introduced as a backward-compatible extension. Existing `run.runner: exe` frozen-folder apps must keep
working.

## Runtime Selection Rules

When a user registers an app, App Studio should determine a dependency lock first, then choose or create a shared runtime.

Priority order:

1. Existing source `requirements.lock`, `uv.lock`, `poetry.lock`, or equivalent lock file.
2. Existing local project virtual environment when it is clearly associated with the selected source root.
3. Direct-run probe of the selected Python environment for packages declared by `requirements.txt`.
4. Exact pins in `requirements.txt`.
5. Fresh resolution from `requirements.txt` only when no known-good version source exists.

Broad requirements such as `flet>=0.23.2` must not automatically mean "install latest" if the app is known to run with a
specific installed version.

For the Flet case:

```text
requirements.txt: flet>=0.23.2
direct-run probe: flet==0.28.3
selected lock:    flet==0.28.3
```

## Environment Identity

Each shared environment needs a stable identity.

Recommended env id input:

- Python major/minor version.
- Platform and architecture.
- Normalized top-level direct dependencies.
- Full resolved `requirements.lock` hash.
- Runtime feature flags such as Playwright browser channel, if applicable.

Human-readable env ids are useful, but collision safety should come from a hash.

Example:

```text
py313-win_amd64-flet0283-pymupdf1271-a8f31c2d
```

The authoritative metadata should live in `toolhub_env_manifest.json`:

```json
{
  "schema_version": 1,
  "env_id": "py313-win_amd64-flet0283-pymupdf1271-a8f31c2d",
  "python_version": "3.13.2",
  "platform": "win_amd64",
  "requirements_lock_sha256": "...",
  "created_at": "2026-05-11T00:00:00",
  "created_for_app_id": "legacy_flet_system_20260510",
  "packages": {
    "flet": "0.28.3",
    "flet-desktop": "0.28.3",
    "pypdf": "6.7.0",
    "PyMuPDF": "1.27.1",
    "pywin32": "310"
  },
  "shared_assets": []
}
```

## Registration Flow

New registration flow:

```text
source selection
-> file inventory and sensitive file exclusion
-> dependency source discovery
-> known-good version probe
-> requirements.lock generation
-> env id calculation
-> shared env lookup
-> create shared env if missing
-> framework/runtime asset setup
-> app.yaml generation
-> startup check by app kind
-> approval
```

Important changes from the current frozen-folder-first flow:

- Dependency lock is decided before runtime creation.
- The lock must represent app runtime dependencies, not build tools.
- Build tools such as PyInstaller must not be written into app `requirements.lock`.
- If an env already exists for the same lock, App Studio reuses it instead of creating a new app-local environment.
- If no env exists, App Studio creates one under `runtime/envs/<env_id>/`.

## App Storage Model

`apps/<app_id>/` remains the source of truth for app metadata and app-owned files.

For shared-runtime apps, `apps/<app_id>/` should contain:

```text
apps/<app_id>/
  app.yaml
  requirements.lock
  build_profile.json
  app.py
  pdf_app/
  assets/
```

It should not contain:

- `.venv/`
- full `site-packages/`
- Playwright browser binaries
- source logs
- auth/session/storage state
- App Studio build temp folders

## Runner Model

Add a runner for shared Python environments:

```yaml
run:
  runner: python_shared_env
  entry: app.py
  mode: gui
  env_id: py313-win_amd64-flet0283-pymupdf1271-a8f31c2d
```

Runner behavior:

- Resolve `runtime/envs/<env_id>/Scripts/python.exe`.
- Set working directory to `apps/<app_id>/`.
- Apply app environment variables.
- For GUI apps, start detached but keep a short stderr/stdout startup probe.
- For CLI apps, run blocking and return exit code.
- For Playwright apps, set browser/profile paths before launch.

Existing runners remain:

- `exe` for frozen-folder apps.
- `cli` for simple blocking scripts.
- `playwright_python` during compatibility transition.
- `python_app_env` for legacy app-env compatibility.

## Flet Policy

Flet apps are sensitive to API changes. App Studio should preserve the known-good Flet version unless the user explicitly
chooses to upgrade.

Rules:

- If the working environment has `flet` installed and source requirements declare `flet`, pin the working version.
- Pin `flet-desktop` to the same version as `flet` when desktop GUI execution is used.
- Do not resolve broad Flet ranges to latest by default.
- Record Flet version in `toolhub_env_manifest.json`.
- Startup check should detect early Flet exceptions from stderr, including `Unhandled error in main()` and constructor
  argument errors.

This avoids the observed `TextField(helper_text=...)` break caused by registering a working Flet 0.28.3 app against
Flet 0.85.0.

## Playwright Policy

Playwright needs two separate concepts:

- Python package dependency: can live in the shared Python env.
- Browser binaries: should live in versioned shared runtime storage.

Recommended layout:

```text
runtime/
  envs/
    py313-playwright1460-...
  shared/
    playwright/
      1.46.0/
        chromium/
        firefox/
        webkit/
```

Rules:

- Do not bundle browser binaries into every app folder.
- Do not copy `.auth/`, cookies, storage state, or user profiles into runtime or app packages.
- Keep browser profile data in user data paths, not app runtime paths.
- If the required Playwright version does not exist in `runtime/shared/playwright/<version>/`, create or install that
  versioned shared runtime through an explicit App Studio/runtime setup step.
- Keep app-facing messages non-technical; keep technical runtime details in logs.

This prevents app-by-app browser duplication while avoiding forced upgrades to one global Playwright version.

## Terminal and CLI Policy

Terminal-driven apps can use the same shared runtime model.

Rules:

- Use `run.mode: cli` for blocking commands.
- Pass stdout/stderr into ToolHub logs.
- Treat exit code `0` as success unless a custom health policy says otherwise.
- Do not require GUI/window checks for CLI apps.
- Preserve working directory and environment variables from app metadata.

## Frozen-Folder Role After This Change

Frozen-folder remains useful but should no longer be the only standard.

Recommended roles:

- Shared versioned runtime: default for local ToolHub-managed apps.
- Frozen-folder: external distribution, portable app packs, or apps that must be self-contained.
- Existing exe: explicit admin-controlled import only, not normal AI/App Studio registration.

This keeps local ToolHub installations smaller when many apps share dependencies, while preserving a portable packaging
path when needed.

## Size Policy

Expected size effects:

- Small CLI shared env: moderate one-time cost, then near-zero cost for additional apps using the same lock.
- Flet shared env: one env per Flet version family instead of one frozen copy per app.
- Playwright: major savings if browser binaries are shared by version.
- PyQt/PySide or OCR/ML apps: may still be large, but repeated apps can reuse compatible envs.

Anti-patterns:

- Copying `.venv` into every app.
- Freezing every Playwright app with browsers bundled inside each app.
- Using one global latest runtime for all apps.
- Writing PyInstaller/build-tool packages into runtime `requirements.lock`.

## Safety and Security

Shared runtime creation must preserve current safety rules:

- Do not package credentials, tokens, `.auth/`, cookies, storage state, browser profiles, logs, temp files, or caches.
- Do not silently download browser/runtime binaries during normal app launch.
- Runtime setup downloads, if supported, should be explicit, logged, and tied to versioned runtime records.
- Runtime deletion must respect reference counts and never remove an env used by an enabled app.
- App deletion must not delete shared runtime by default.

## Runtime Reference Tracking

ToolHub should track which apps use each shared runtime.

Example registry:

```json
{
  "schema_version": 1,
  "envs": {
    "py313-win_amd64-flet0283-pymupdf1271-a8f31c2d": {
      "path": "runtime/envs/py313-win_amd64-flet0283-pymupdf1271-a8f31c2d",
      "requirements_lock_sha256": "...",
      "apps": ["legacy_flet_system_20260510"],
      "last_used_at": "2026-05-11T00:00:00"
    }
  }
}
```

Deletion behavior:

- Removing an app removes only the app's own files by default.
- Unused runtime cleanup should be a separate admin operation.
- Runtime cleanup should show affected env ids, sizes, and app reference counts.

## Validation Strategy

Validation should confirm that the selected runtime can run the app, but it should not become a large unrelated test
suite.

Minimum checks by kind:

- Flet GUI:
  - selected env contains pinned `flet` and matching `flet-desktop`
  - app starts without immediate stderr traceback
  - process remains alive beyond startup probe
- Playwright:
  - selected env imports `playwright`
  - required browser runtime version exists or is clearly reported missing
  - auth/session data is not packaged
- CLI:
  - process exits with expected code
  - stdout/stderr are captured
- Generic GUI:
  - process starts
  - immediate crash and traceback are detected

Avoid unrelated checks. A Flet app should not fail because Playwright browser setup is absent. A CLI app should not fail
because no GUI window was detected.

## Migration Plan

Phase 1: Document and model

- Add shared runtime design docs.
- Add schema proposal for `runtime.shared_env`.
- Keep current frozen-folder behavior unchanged.

Phase 2: Dependency lock correction

- Change lock generation to prefer known-good versions.
- Prevent build tool packages from entering app `requirements.lock`.
- Add direct-run environment probe for declared packages.

Phase 3: Shared env builder

- Create `runtime/envs/<env_id>/` from lock.
- Add env manifest.
- Add env lookup/reuse by lock hash.

Phase 4: Runner support

- Add `python_shared_env` runner.
- Support `gui`, `cli`, and `background` modes.
- Preserve current `exe` runner compatibility.

Phase 5: App Studio integration

- Let App Studio choose existing env or create a new one.
- Show the selected env and dependency versions in admin UI.
- If a new version set is needed, create a new shared runtime and record it.

Phase 6: Playwright shared runtime

- Move browser binaries to `runtime/shared/playwright/<version>/`.
- Update Playwright runner environment variables.
- Keep browser profiles and storage state in user data paths.

Phase 7: Cleanup and release policy

- Add runtime reference tracking.
- Add admin cleanup for unused runtimes.
- Update release verification to understand shared runtime apps.

## Compatibility Requirements

The implementation must not break:

- Existing frozen-folder apps with `run.runner: exe`.
- Existing app packs already generated from `apps/<app_id>/`.
- Existing legacy app-env manifests.
- Current deletion safety rules around shared runtime folders.
- Existing user data, logs, browser profiles, and app state.

## Open Decisions

The following should be decided during implementation:

- Exact env id naming format.
- Whether App Studio may create shared envs inside release builds immediately, or first behind an admin setting.
- How runtime archives are prepared for offline/installer distribution.
- Whether direct-run probe should use system `python`, selected interpreter, or detected `.venv` first.
- How to handle apps whose direct-run environment contains packages not declared in requirements.

## Recommended Next Step

Implement Phase 2 first. The immediate failure can be addressed by fixing dependency lock generation before changing the
runner model:

- Probe the direct-run environment for packages declared in `requirements.txt`.
- Pin known-good versions into `requirements.lock`.
- Exclude build-only packages from app locks.
- Keep the current frozen-folder runner until shared env runner is ready.

After that, implement shared env creation and `python_shared_env` as the new standard registration path.
