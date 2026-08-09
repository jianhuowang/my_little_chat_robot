param([string]$RuntimeDir = "runtime\astrbot")
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
