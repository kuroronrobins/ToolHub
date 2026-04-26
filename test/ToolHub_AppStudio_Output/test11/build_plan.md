# Build Plan

- app_id: `test11`
- name: `Test12`
- selected_mode: `app-env`
- runner: `python_app_env`
- entry: `src/main.py`

## Reasons

- Simple Python entry and dependency profile.

## app_env Layout

- Runtime: `runtime/app_envs/test11/Scripts/python.exe`
- Fallback runtime: `runtime/python/python.exe`
- User PATH Python is not required for the imported app.
