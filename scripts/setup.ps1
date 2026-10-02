param(
    [string]$GameRoot = '',
    [ValidateSet('openai', 'deepseek')][string]$Provider = 'openai',
    [switch]$Offline
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).ProviderPath
$toolsRoot = Join-Path $projectRoot '.tools'

function Find-GameDirectory {
    param([string]$ExplicitPath)
    if ($ExplicitPath) {
        $resolved = (Resolve-Path -LiteralPath $ExplicitPath).ProviderPath
        $candidates = @($resolved)
    } else {
        $steamRoots = @("${env:ProgramFiles(x86)}\Steam")
        foreach ($key in @('HKCU:\Software\Valve\Steam', 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam')) {
            $entry = Get-ItemProperty -LiteralPath $key -ErrorAction SilentlyContinue
            if ($entry.SteamPath) { $steamRoots += $entry.SteamPath }
            if ($entry.InstallPath) { $steamRoots += $entry.InstallPath }
        }
        $libraries = @($steamRoots)
        foreach ($steamRoot in $steamRoots) {
            $vdf = Join-Path $steamRoot 'steamapps/libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf) {
                $text = Get-Content -LiteralPath $vdf -Raw
                foreach ($match in [regex]::Matches($text, '"path"\s+"([^"\r\n]+)"')) {
                    $libraries += $match.Groups[1].Value.Replace('\\', '\')
                }
            }
        }
        $candidates = @($libraries | Select-Object -Unique | ForEach-Object {
            Join-Path $_ 'steamapps/common/Slay the Spire 2'
        })
    }
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath (Join-Path $candidate 'Slay the Spire 2.exe')) -or
            (Test-Path -LiteralPath (Join-Path $candidate 'SlayTheSpire2.exe'))) {
            return (Resolve-Path -LiteralPath $candidate).ProviderPath
        }
    }
    throw 'Game not found. Pass -GameRoot "D:\SteamLibrary\steamapps\common\Slay the Spire 2", or use -Offline.'
}

function Invoke-Installer {
    param([string]$Url, [string]$FileName, [string[]]$Arguments = @())
    New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
    $download = Join-Path $toolsRoot $FileName
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $download
    # Official installers may exit; isolate them from this setup process.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $download @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Installer failed: $FileName" }
}

if (-not $Offline) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'Git is required for the pinned bridge. Install Git for Windows and open a new terminal.'
    }
    $gameDirectory = Find-GameDirectory $GameRoot
    if (Get-Process -Name 'SlayTheSpire2', 'Slay the Spire 2' -ErrorAction SilentlyContinue) {
        throw 'Close Slay the Spire 2 before setup installs the bridge.'
    }
}

$localUv = Join-Path $toolsRoot 'uv/uv.exe'
if (Test-Path -LiteralPath $localUv) {
    $uvExecutable = $localUv
} elseif (Get-Command uv -ErrorAction SilentlyContinue) {
    $uvExecutable = (Get-Command uv).Source
} else {
    $env:UV_INSTALL_DIR = Join-Path $toolsRoot 'uv'
    $env:UV_NO_MODIFY_PATH = '1'
    Invoke-Installer 'https://astral.sh/uv/install.ps1' 'install-uv.ps1'
    $uvExecutable = $localUv
}
if (-not (Test-Path -LiteralPath $uvExecutable)) { throw 'uv installation did not produce uv.exe.' }

Push-Location -LiteralPath $projectRoot
try {
    & $uvExecutable sync --locked --no-dev --python 3.13 --cache-dir (Join-Path $projectRoot '.uv-cache')
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    foreach ($pair in @(
        @('.env.example', '.env'),
        @($(if ($Provider -eq 'deepseek') { 'config.deepseek.example.toml' } else { 'config.example.toml' }), 'config.local.toml')
    )) {
        $target = Join-Path $projectRoot $pair[1]
        if (-not (Test-Path -LiteralPath $target)) {
            Copy-Item -LiteralPath (Join-Path $projectRoot $pair[0]) -Destination $target
        }
    }

    if (-not $Offline) {
        $dotnetDirectory = Join-Path $toolsRoot 'dotnet'
        $localDotnet = Join-Path $dotnetDirectory 'dotnet.exe'
        if (Test-Path -LiteralPath $localDotnet) {
            $env:PATH = $dotnetDirectory + [IO.Path]::PathSeparator + $env:PATH
        }
        $hasSdk = $false
        if (Get-Command dotnet -ErrorAction SilentlyContinue) {
            $hasSdk = [bool]((& dotnet --list-sdks) -match '^9\.')
        }
        if (-not $hasSdk) {
            Invoke-Installer 'https://dot.net/v1/dotnet-install.ps1' 'dotnet-install.ps1' @(
                '-Channel', '9.0', '-InstallDir', $dotnetDirectory, '-NoPath'
            )
            $env:PATH = $dotnetDirectory + [IO.Path]::PathSeparator + $env:PATH
            if (-not (Test-Path -LiteralPath $localDotnet)) { throw '.NET installation failed.' }
        }
        & (Join-Path $PSScriptRoot 'prepare-bridge.ps1') -GameRoot $gameDirectory -Install
    }
    & (Join-Path $projectRoot '.venv/Scripts/python.exe') -m spiremind --help
    if ($LASTEXITCODE -ne 0) { throw 'Installed SpireMind CLI failed verification.' }
    Write-Output 'Setup complete. Fill .env and config.local.toml, then run .\spiremind.cmd start.'
    if (-not $Offline) { Write-Output 'Start the game from Steam, enable STS2AIMCP, and return to the main menu.' }
} finally {
    Pop-Location
}
