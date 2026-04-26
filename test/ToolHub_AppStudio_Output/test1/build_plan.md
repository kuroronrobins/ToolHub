# Build Plan

- app_id: `test1`
- name: `Test2`
- selected_mode: `app-env`
- runner: `python_app_env`
- entry: `src/main.py`

## Reasons

- Simple Python entry and dependency profile.

## app_env Layout

- Runtime: `runtime/app_envs/test1/Scripts/python.exe`
- Fallback runtime: `runtime/python/python.exe`
- User PATH Python is not required for the imported app.
