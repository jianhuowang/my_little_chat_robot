$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $repoRoot
try {
    uv run qq-deepseek-setup balance
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $exitCode
