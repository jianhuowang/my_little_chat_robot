$ErrorActionPreference = "Stop"

function Assert-NoReparsePoint {
    param([string]$Root, [string]$Path, [string]$SettingName)
    $relativePath = $Path.Substring($Root.Length).TrimStart([char[]]@("\", "/"))
    $current = $Root
    foreach ($segment in $relativePath.Split([char[]]@("\", "/"), [System.StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path $current $segment
        if (-not (Test-Path -LiteralPath $current)) { break }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$SettingName must not traverse a reparse point"
        }
    }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repoRoot ".env"
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) { throw ".env is missing" }
Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
}
$runtimeDir = if ($env:ASTRBOT_RUNTIME_DIR) { $env:ASTRBOT_RUNTIME_DIR } else { "runtime\astrbot" }
$target = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $runtimeDir))
if (-not $target.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ASTRBOT_RUNTIME_DIR must stay inside the repository"
}
Assert-NoReparsePoint -Root $repoRoot -Path $target -SettingName "ASTRBOT_RUNTIME_DIR"
if (-not (Test-Path -LiteralPath $target -PathType Container)) { throw "AstrBot runtime is not initialized" }
Push-Location $target
try {
    astrbot run
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
