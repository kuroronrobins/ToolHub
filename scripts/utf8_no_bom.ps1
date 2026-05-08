function New-Utf8NoBomEncoding {
    return New-Object System.Text.UTF8Encoding -ArgumentList $false
}

function Write-Utf8NoBomFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Content
    )

    $FullPath = [System.IO.Path]::GetFullPath($Path)
    $Directory = [System.IO.Path]::GetDirectoryName($FullPath)
    if ($Directory -and -not (Test-Path -LiteralPath $Directory -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $Directory | Out-Null
    }

    [System.IO.File]::WriteAllText($FullPath, $Content, (New-Utf8NoBomEncoding))
}

function Write-JsonUtf8NoBomFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [AllowNull()]
        [object]$InputObject,

        [int]$Depth = 20
    )

    $Json = $InputObject | ConvertTo-Json -Depth $Depth
    Write-Utf8NoBomFile -Path $Path -Content ($Json + "`n")
}

function Test-Utf8Bom {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    $Bytes = [System.IO.File]::ReadAllBytes([System.IO.Path]::GetFullPath($Path))
    return ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF)
}
