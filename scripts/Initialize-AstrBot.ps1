param([string]$RuntimeDir = "runtime\astrbot")
$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = [System.IO.Path]::GetFullPath((Join-Path $resolvedRoot $RuntimeDir))
if (-not $target.StartsWith($resolvedRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "RuntimeDir must stay inside the repository"
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
Push-Location $target
try {
    astrbot init
} finally {
    Pop-Location
}
