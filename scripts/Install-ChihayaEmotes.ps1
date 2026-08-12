param(
    [Parameter(Mandatory = $true)]
    [string[]]$SourceDir,
    [string]$RuntimeDir = "runtime\astrbot"
)
$ErrorActionPreference = "Stop"

function Assert-InsideRepository {
    param([string]$Root, [string]$Path, [string]$SettingName)
    if (-not $Path.StartsWith($Root + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$SettingName must stay inside the repository"
    }
}

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
$runtime = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $RuntimeDir))
Assert-InsideRepository -Root $repoRoot -Path $runtime -SettingName "RuntimeDir"
Assert-NoReparsePoint -Root $repoRoot -Path $runtime -SettingName "RuntimeDir"

$pluginSource = (Resolve-Path (Join-Path $repoRoot "plugins\chihaya_emotes")).Path
$pluginTarget = [System.IO.Path]::GetFullPath((Join-Path $runtime "data\plugins\chihaya_emotes"))
Assert-InsideRepository -Root $repoRoot -Path $pluginSource -SettingName "Plugin source"
Assert-InsideRepository -Root $repoRoot -Path $pluginTarget -SettingName "Plugin destination"
Assert-NoReparsePoint -Root $repoRoot -Path $pluginSource -SettingName "Plugin source"
Assert-NoReparsePoint -Root $repoRoot -Path $pluginTarget -SettingName "Plugin destination"

$runningAstrBot = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine.IndexOf($runtime, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
    $_.CommandLine -match '(?i)astrbot'
}
if ($runningAstrBot) { throw "AstrBot must be stopped for the selected runtime" }

New-Item -ItemType Directory -Path $pluginTarget -Force | Out-Null
Assert-NoReparsePoint -Root $repoRoot -Path $pluginTarget -SettingName "Plugin destination"
$pluginFiles = @(
    "__init__.py",
    "_conf_schema.json",
    "controller.py",
    "image_pool.py",
    "main.py",
    "metadata.yaml",
    "quota.py",
    "settings.py",
    "trigger.py"
)
foreach ($pluginFile in $pluginFiles) {
    Copy-Item -LiteralPath (Join-Path $pluginSource $pluginFile) -Destination (Join-Path $pluginTarget $pluginFile) -Force
}

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Repository virtualenv Python is missing" }
$sourceArguments = @()
foreach ($source in $SourceDir) {
    $sourceArguments += "--source"
    $sourceArguments += $source
}
& $python -m qq_deepseek_setup.cli install-emotes `
    @sourceArguments `
    --destination (Join-Path $pluginTarget "emotes") `
    --allowed-root $runtime
exit $LASTEXITCODE
