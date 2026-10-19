<#
AI HR Assistant v8.8.249 — optional one-time housekeeping only.
By default: preview paths. With -Apply: MOVE known obsolete files into a
new sibling backup directory (no permanent deletion).

Run from C:\User_dev\HR_Assistant:
  .\AI_HR_Assistant_v8.8.249_Safe_Cleanup.ps1
  .\AI_HR_Assistant_v8.8.249_Safe_Cleanup.ps1 -Apply

If saved elsewhere:
  .\AI_HR_Assistant_v8.8.249_Safe_Cleanup.ps1 -ProjectPath 'C:\User_dev\HR_Assistant' -Apply
#>
[CmdletBinding()]
param(
    [string]$ProjectPath = (Get-Location).Path,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ProjectPath).Path
$mustExist = @(
    'app.py',
    'modules\smart_ai\portal_ai.py',
    'schemas\__init__.py',
    'schemas\policy_schema.py',
    'config\settings.py'
)
foreach ($relative in $mustExist) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $relative) -PathType Leaf)) {
        throw "Not a compatible AI HR Assistant project; missing $relative in $root. No changes were made."
    }
}

$oldFolders = @(
    'admin', 'assets', 'authentication', 'config', 'core', 'database',
    'deploy', 'integrations', 'knowledge', 'models', 'modules',
    'repositories', 'schemas', 'scripts', 'services', 'tests', 'ui', 'utils'
)
$oldSchemaFiles = @('.env.example', '.gitignore', 'DEVELOPER_GUIDE.md', 'alembic.ini', 'app.py')
$oldRootFiles = @(
    'RELEASE_NOTES_v8.8.244.md',
    'RELEASE_NOTES_v8.8.245.md',
    'RELEASE_NOTES_v8.8.246.md',
    'RELEASE_NOTES_v8.8.247.md',
    'RELEASE_NOTES_v8.8.248.md',
    'QA_Focused_Retest_v8.8.248.md'
)
$targets = @()
foreach ($name in $oldFolders) {
    $targets += (Join-Path 'schemas' $name)
}
foreach ($name in $oldSchemaFiles) {
    $targets += (Join-Path 'schemas' $name)
}
$targets += $oldRootFiles

# Also capture old release ZIPs if a user accidentally left them in the project root.
# DO NOT match current 249 or newer or any unrelated user files.
$oldPackageRegex = '^AI_HR_Assistant_v8\.8\.(244|245|246|247|248)_(Patch_Only|Data_Safe_Full_Code)\.zip$'
foreach ($file in (Get-ChildItem -LiteralPath $root -File -ErrorAction SilentlyContinue)) {
    if ($file.Name -match $oldPackageRegex) {
        $targets += $file.Name
    }
}

$existing = @($targets | Where-Object { Test-Path -LiteralPath (Join-Path $root $_) })
Write-Host "Project: $root"
Write-Host "Known obsolete paths found: $($existing.Count)"
foreach ($relative in $existing) {
    Write-Host "  [OLD] $relative"
}
if ($existing.Count -eq 0) {
    Write-Host 'Nothing to clean.'
    return
}
if (-not $Apply) {
    Write-Host ''
    Write-Host 'DRY RUN: No files were changed.'
    Write-Host 'Back up the project and stop Streamlit before running with -Apply.'
    return
}

# Back up outside the live application; preserving local changes in any old subtree.
$projectParent = Split-Path -Parent $root
$backupLabel = 'HR_Assistant_Legacy_Backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,6)
$backup = Join-Path $projectParent $backupLabel
New-Item -Path $backup -ItemType Directory -Force | Out-Null
foreach ($relative in $existing) {
    $source = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $source)) { continue }
    $destination = Join-Path $backup $relative
    $destinationParent = Split-Path -Parent $destination
    New-Item -Path $destinationParent -ItemType Directory -Force | Out-Null
    Move-Item -LiteralPath $source -Destination $destination -ErrorAction Stop
    Write-Host "  [MOVED TO BACKUP] $relative"
}
Write-Host ''
Write-Host 'Housekeeping completed (no permanent deletion).'
Write-Host "Backup location: $backup"
Write-Host 'Active app.py, modules, schemas/*_schema.py, tests, .env, data, DB, Qdrant, logs, and the latest v8.8.249 notes were left untouched.'
Write-Host 'Next: run the existing regression tests before starting Streamlit.'
