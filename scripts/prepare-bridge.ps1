param(
    [Parameter(Mandatory = $true)][string]$GameRoot,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).ProviderPath
$gameDirectory = (Resolve-Path -LiteralPath $GameRoot).ProviderPath
$bridgeLock = Get-Content -LiteralPath (Join-Path $projectRoot 'bridge.lock.json') -Raw | ConvertFrom-Json
$referenceRoot = Join-Path $projectRoot 'references'
$checkout = Join-Path $referenceRoot 'sts2-ai-mcp'
$patchFile = Join-Path $projectRoot $bridgeLock.patch
$outputDirectory = Join-Path $projectRoot 'build/mods'

if ($Install -and (Get-Process -Name 'SlayTheSpire2', 'Slay the Spire 2' -ErrorAction SilentlyContinue)) {
    throw 'Close Slay the Spire 2 before installing the bridge.'
}
if (-not (Test-Path -LiteralPath $checkout)) {
    New-Item -ItemType Directory -Path $referenceRoot -Force | Out-Null
    git clone $bridgeLock.repository $checkout
    if ($LASTEXITCODE -ne 0) { throw 'Bridge clone failed.' }
    git -C $checkout checkout --detach $bridgeLock.commit
    if ($LASTEXITCODE -ne 0) { throw 'Pinned bridge checkout failed.' }
}
$actualCommit = git -C $checkout rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $actualCommit.Trim() -ne $bridgeLock.commit) {
    throw 'Existing bridge checkout is not at the pinned commit. Preserve local work and use a matching checkout.'
}
git -C $checkout apply --reverse --check $patchFile 2>$null
if ($LASTEXITCODE -ne 0) {
    git -C $checkout apply --check $patchFile
    if ($LASTEXITCODE -ne 0) { throw 'Bridge patch cannot be applied cleanly.' }
    git -C $checkout apply $patchFile
    if ($LASTEXITCODE -ne 0) { throw 'Bridge patch failed.' }
}
& (Join-Path $checkout 'scripts/build-mod.ps1') -Configuration Release -GameRoot $gameDirectory -ModsDir $outputDirectory
if ($LASTEXITCODE -ne 0) { throw 'Bridge build failed.' }
$builtMod = Join-Path $outputDirectory 'STS2AIMCP'
$fileNames = @('STS2AIMCP.dll', 'STS2AIMCP.json', 'STS2AIMCP.pck')
foreach ($fileName in $fileNames) {
    if (-not (Test-Path -LiteralPath (Join-Path $builtMod $fileName))) { throw "Missing artifact: $fileName" }
}
if ($Install) {
    if (Get-Process -Name 'SlayTheSpire2', 'Slay the Spire 2' -ErrorAction SilentlyContinue) {
        throw 'Game started during build. Close it before installation.'
    }
    $destination = Join-Path $gameDirectory 'mods/STS2AIMCP'
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    foreach ($fileName in $fileNames) {
        $sourceFile = Join-Path $builtMod $fileName
        $destinationFile = Join-Path $destination $fileName
        Copy-Item -LiteralPath $sourceFile -Destination $destinationFile -Force
        if ((Get-FileHash -LiteralPath $sourceFile).Hash -ne (Get-FileHash -LiteralPath $destinationFile).Hash) {
            throw "Installed artifact hash mismatch: $fileName"
        }
    }
    Write-Output "Installed bridge: $destination"
} else {
    Write-Output "Built bridge: $builtMod"
}
