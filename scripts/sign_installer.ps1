param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$CertificateThumbprint,
    [string]$CertificateSubject,
    [string]$TimestampUrl,
    [string]$SignToolPath,
    [string[]]$SignToolExtraArgs = @(),
    [string]$FileDigestAlgorithm = "SHA256",
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Resolve-InstallerPath {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Installer path is required."
    }
    if (-not (Test-Path -LiteralPath $Value -PathType Leaf)) {
        throw "Installer file was not found: $Value"
    }
    return (Resolve-Path -LiteralPath $Value).Path
}

function Resolve-SignTool {
    param([string]$ConfiguredPath)

    if (-not [string]::IsNullOrWhiteSpace($ConfiguredPath)) {
        if (-not (Test-Path -LiteralPath $ConfiguredPath -PathType Leaf)) {
            throw "SignTool was not found: $ConfiguredPath"
        }
        return (Resolve-Path -LiteralPath $ConfiguredPath).Path
    }

    $Command = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $ProgramFilesX86 = ${env:ProgramFiles(x86)}
    $WindowsKitsRoot = if (-not [string]::IsNullOrWhiteSpace($ProgramFilesX86)) {
        Join-Path $ProgramFilesX86 "Windows Kits\10\bin"
    } else {
        ""
    }
    if (-not [string]::IsNullOrWhiteSpace($WindowsKitsRoot) -and (Test-Path -LiteralPath $WindowsKitsRoot -PathType Container)) {
        $Candidates = Get-ChildItem -LiteralPath $WindowsKitsRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\signtool.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
        $First = @($Candidates | Select-Object -First 1)
        if ($First.Count -gt 0) {
            return $First[0]
        }
    }

    throw "signtool.exe was not found. Install Windows SDK or pass -SignToolPath."
}

function Assert-ValidSignature {
    param([string]$InstallerPath)

    $Signature = Get-AuthenticodeSignature -LiteralPath $InstallerPath
    if ($Signature.Status -ne "Valid") {
        throw "Installer Authenticode signature is not valid. status=$($Signature.Status) path=$InstallerPath"
    }

    $Subject = if ($Signature.SignerCertificate) { $Signature.SignerCertificate.Subject } else { "" }
    $Thumbprint = if ($Signature.SignerCertificate) { $Signature.SignerCertificate.Thumbprint } else { "" }
    Write-Host "[OK] Installer signature is valid."
    if (-not [string]::IsNullOrWhiteSpace($Subject)) {
        Write-Host "Signer: $Subject"
    }
    if (-not [string]::IsNullOrWhiteSpace($Thumbprint)) {
        Write-Host "Thumbprint: $Thumbprint"
    }
}

$InstallerPath = Resolve-InstallerPath -Value $Path

if ($VerifyOnly) {
    Assert-ValidSignature -InstallerPath $InstallerPath
    exit 0
}

if ([string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    $CertificateThumbprint = $env:TOOLHUB_CODESIGN_CERT_THUMBPRINT
}
if ([string]::IsNullOrWhiteSpace($CertificateSubject)) {
    $CertificateSubject = $env:TOOLHUB_CODESIGN_CERT_SUBJECT
}
if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
    $TimestampUrl = $env:TOOLHUB_CODESIGN_TIMESTAMP_URL
}
if ([string]::IsNullOrWhiteSpace($TimestampUrl)) {
    $TimestampUrl = "http://timestamp.digicert.com"
}
if ([string]::IsNullOrWhiteSpace($SignToolPath)) {
    $SignToolPath = $env:TOOLHUB_SIGNTOOL_PATH
}

$HasCertificateSelector =
    (-not [string]::IsNullOrWhiteSpace($CertificateThumbprint)) -or
    (-not [string]::IsNullOrWhiteSpace($CertificateSubject))
$HasCustomSigningArgs = @($SignToolExtraArgs).Count -gt 0
if (-not $HasCertificateSelector -and -not $HasCustomSigningArgs) {
    throw "Provide -CertificateThumbprint, -CertificateSubject, -SignToolExtraArgs, or TOOLHUB_CODESIGN_CERT_THUMBPRINT."
}

$ResolvedSignTool = Resolve-SignTool -ConfiguredPath $SignToolPath
$Arguments = @("sign", "/v", "/fd", $FileDigestAlgorithm)
if (-not [string]::IsNullOrWhiteSpace($TimestampUrl)) {
    $Arguments += @("/tr", $TimestampUrl, "/td", $FileDigestAlgorithm)
}
if (-not [string]::IsNullOrWhiteSpace($CertificateThumbprint)) {
    $Arguments += @("/sha1", $CertificateThumbprint)
} elseif (-not [string]::IsNullOrWhiteSpace($CertificateSubject)) {
    $Arguments += @("/n", $CertificateSubject)
}
if ($HasCustomSigningArgs) {
    $Arguments += $SignToolExtraArgs
}
$Arguments += $InstallerPath

Write-Host "Signing installer: $InstallerPath"
Write-Host "SignTool: $ResolvedSignTool"
& $ResolvedSignTool @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "signtool.exe failed with exit code $LASTEXITCODE."
}

Assert-ValidSignature -InstallerPath $InstallerPath
