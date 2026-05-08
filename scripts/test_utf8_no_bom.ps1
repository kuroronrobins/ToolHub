$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "utf8_no_bom.ps1")

function Assert-Condition {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("toolhub_utf8_no_bom_" + [System.Guid]::NewGuid().ToString("N"))

try {
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

    $TextPath = Join-Path $TempDir "plain.json"
    Write-Utf8NoBomFile -Path $TextPath -Content "{`"ok`":true}`n"
    Assert-Condition -Condition (-not (Test-Utf8Bom -Path $TextPath)) -Message "Write-Utf8NoBomFile wrote a UTF-8 BOM."

    $JsonPath = Join-Path $TempDir "object.json"
    $NonAsciiMessage = [string]::Concat([char]0x65E5, [char]0x672C, [char]0x8A9E)
    Write-JsonUtf8NoBomFile -Path $JsonPath -InputObject ([ordered]@{
        ok = $true
        message = $NonAsciiMessage
    }) -Depth 5
    Assert-Condition -Condition (-not (Test-Utf8Bom -Path $JsonPath)) -Message "Write-JsonUtf8NoBomFile wrote a UTF-8 BOM."

    $Parsed = Get-Content -Raw -Encoding UTF8 $JsonPath | ConvertFrom-Json
    Assert-Condition -Condition ($Parsed.ok -eq $true) -Message "UTF-8 no BOM JSON did not parse correctly."
    Assert-Condition -Condition ($Parsed.message -eq $NonAsciiMessage) -Message "UTF-8 no BOM JSON did not preserve non-ASCII text."

    Write-Host "OK: UTF-8 no BOM helper writes JSON without BOM."
}
finally {
    if (Test-Path -LiteralPath $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force
    }
}
