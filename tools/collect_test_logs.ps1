[CmdletBinding()]
param(
    [ValidateSet('B0','B1','B2','B3','B4','C1')][string]$Run = 'C1',
    [string]$Note = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$documentsPath = [Environment]::GetFolderPath('MyDocuments')
$dataRoot = Join-Path $documentsPath 'Paradox Interactive\Victoria 3'
$runFolder = Join-Path $projectRoot ('runtime\manual-' + $Run + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $runFolder) { throw "Destination already exists: $runFolder" }
New-Item -ItemType Directory -Path $runFolder | Out-Null
$logSource = Join-Path $dataRoot 'logs'
if (Test-Path -LiteralPath $logSource) {
    Copy-Item -LiteralPath $logSource -Destination (Join-Path $runFolder 'logs') -Recurse
}
foreach ($relative in @('content_load.json','game_data.json')) {
    $source = Join-Path $dataRoot $relative
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $runFolder }
}
$info = [ordered]@{
    Run = $Run
    CollectedUtc = (Get-Date).ToUniversalTime().ToString('o')
    DataRoot = $dataRoot
    Note = $Note
    Result = 'NOT_EVALUATED'
    GameLaunchedByCollector = $false
    SavesCopied = $false
}
$info | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runFolder 'run.json') -Encoding UTF8
Write-Output "Logs copied to: $runFolder"
