param(
    [Parameter(Mandatory = $true)]
    [string]$AppId,

    [Parameter(Mandatory = $true)]
    [string]$Name
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$AppDir = Join-Path (Join-Path $Root "apps") $AppId

if ($AppId -notmatch '^[a-zA-Z0-9_-]+$') {
    Write-Error "AppId can use only letters, numbers, hyphens, and underscores."
}

if (Test-Path $AppDir) {
    Write-Error "App folder already exists: $AppDir"
}

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

@"
id: $AppId
name: $Name

display:
  icon: icon.svg
  short_description: Add a short description here.
  categories:
    - Uncategorized

detail:
  description: >
    Add the app overview here.
  use_cases:
    - Add a use case
  inputs:
    - Input
  outputs:
    - Output
  notes:
    - Note

search:
  keywords:
    - $Name
  examples:
    - Open $Name

run:
  runner: python
  entry: main.py
  mode: gui

admin:
  version: 1.0.0
  owner: admin
  requirements: requirements.txt
  log_dir: logs
"@ | Set-Content -Encoding UTF8 (Join-Path $AppDir "app.yaml")

@"
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations


def main() -> None:
    print("$Name")


if __name__ == "__main__":
    main()
"@ | Set-Content -Encoding UTF8 (Join-Path $AppDir "main.py")

@"
# $Name

ToolHub用アプリテンプレートです。
"@ | Set-Content -Encoding UTF8 (Join-Path $AppDir "README.md")

"# Add required dependencies here." | Set-Content -Encoding UTF8 (Join-Path $AppDir "requirements.txt")

@"
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" role="img" aria-label="$Name">
  <rect x="10" y="10" width="44" height="44" rx="8" fill="#0f766e"/>
  <path d="M22 34l7 7 14-18" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"@ | Set-Content -Encoding UTF8 (Join-Path $AppDir "icon.svg")

Write-Host "App template created: $AppDir"
