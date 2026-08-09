param([string]$RuntimeDir)
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

$resolvedRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeWasSupplied = $PSBoundParameters.ContainsKey("RuntimeDir")
if (-not $runtimeWasSupplied) {
    $RuntimeDir = "runtime\astrbot"
    $envFile = Join-Path $resolvedRoot ".env"
    if (Test-Path -LiteralPath $envFile -PathType Leaf) {
        Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]*)=(.*)$' -and $matches[1].Trim() -eq "ASTRBOT_RUNTIME_DIR") {
                $RuntimeDir = $matches[2].Trim()
            }
        }
    }
}
$target = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot $RuntimeDir))
if (-not $target.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "RuntimeDir must stay inside the repository"
}
Assert-NoReparsePoint -Root $resolvedRoot -Path $target -SettingName "RuntimeDir"
New-Item -ItemType Directory -Path $target -Force | Out-Null
Assert-NoReparsePoint -Root $resolvedRoot -Path $target -SettingName "RuntimeDir"
Push-Location $target
try {
    astrbot init
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
