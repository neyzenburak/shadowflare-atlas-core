param(
    [switch]$CheckOnly, [switch]$SetupOnly, [switch]$RebuildAssets, [switch]$NoShortcut, [switch]$Package,
    [string]$GamePath,
    [switch]$LaunchGame, [int]$Width=0, [int]$Height=0
)
$ErrorActionPreference = 'Stop'
$launcherRoot = $PSScriptRoot
$atlasRoot = Join-Path $launcherRoot 'app'
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'

function Find-AtlasPython {
    $candidates = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue) { $candidates += @{Exe='py.exe'; Args=@('-3')} }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) { $candidates += @{Exe='python.exe'; Args=@()} }
    $pythonRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $pythonRoot) {
        $candidates += @(Get-ChildItem -LiteralPath $pythonRoot -Directory | Sort-Object Name -Descending | ForEach-Object {
            @{Exe=(Join-Path $_.FullName 'python.exe'); Args=@()}
        })
    }
    foreach ($candidate in $candidates) {
        try {
            $pythonArgs = @($candidate.Args) + @('-c', 'import sys; print(sys.executable) if sys.version_info >= (3,9) else sys.exit(1)')
            $output = & $candidate.Exe @pythonArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and $output) {
                $pythonPath = [string](@($output)[-1])
                if (Test-Path -LiteralPath $pythonPath) { return $pythonPath }
            }
        } catch { }
    }
    return $null
}

function Install-AtlasPython {
    Write-Host 'Python is missing. Installing Python for the current Windows user...'
    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        & winget.exe install --id Python.Python.3.14 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity | Out-Host
        $found = Find-AtlasPython
        if ($found) { return $found }
        Write-Host 'Trying the signed installer from python.org...'
    }
    if (!$env:LOCALAPPDATA) { throw 'LOCALAPPDATA is unavailable; install Python 3.9+ and run start.cmd again.' }
    $cache = Join-Path $env:LOCALAPPDATA 'ShadowFlareAtlas\installers'
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    $installer = Join-Path $cache 'python-3.14.10-amd64.exe'
    $expected = '92480239264744fe0386a1bd8275786fefa126e3129e56a68e22b52c73329965'
    if (!(Test-Path -LiteralPath $installer) -or (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.14.10/python-3.14.10-amd64.exe' -OutFile $installer
    }
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Python download checksum failed. No installer was run.' }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') { throw 'Python installer signature verification failed.' }
    $process = Start-Process -FilePath $installer -ArgumentList @('/quiet','InstallAllUsers=0','PrependPath=0','Include_launcher=0','Include_test=0') -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -notin @(0,3010)) { throw "Python installation failed ($($process.ExitCode))." }
    $found = Find-AtlasPython
    if (!$found) { throw 'Python was installed but was not detected. Run start.cmd again.' }
    return $found
}

function Get-AtlasGame([bool]$AllowPicker) {
    $arguments = @((Join-Path $atlasRoot 'game_paths.py'),'locate')
    if ($GamePath) { $arguments += @('--game',$GamePath) }
    $output = & $atlasPython @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Game folder validation failed. No game files were changed.' }
    $found = ($output | ConvertFrom-Json).gamePath
    if (!$found -and $AllowPicker) {
        Write-Host 'Select ShadowFlare.exe in your game installation folder...'
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.OpenFileDialog
        try {
            $picker.Title = 'ShadowFlare Atlas - Select ShadowFlare.exe'
            $picker.Filter = 'ShadowFlare game|ShadowFlare.exe'
            $picker.CheckFileExists = $true
            $picker.RestoreDirectory = $true
            if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'Game selection cancelled. Run start.cmd again when ready.' }
            $output = & $atlasPython (Join-Path $atlasRoot 'game_paths.py') locate --game $picker.FileName
            if ($LASTEXITCODE -ne 0) { throw 'Unsupported game installation selected.' }
            $found = ($output | ConvertFrom-Json).gamePath
        } finally { $picker.Dispose() }
    }
    if ($found -and !$CheckOnly) {
        & $atlasPython (Join-Path $atlasRoot 'game_paths.py') remember --game $found | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not save the selected game folder.' }
    }
    return $found
}

function Install-AtlasBuildTools {
    $venv = Join-Path $launcherRoot '.setup-venv'
    $python = Join-Path $venv 'Scripts\python.exe'
    if (!(Test-Path -LiteralPath $python)) {
        & $atlasPython -m venv $venv | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated asset-builder environment.' }
    }
    $requirements = Join-Path $launcherRoot 'requirements-setup.txt'
    $marker = Join-Path $venv 'atlas-requirements.sha256'
    $hash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    $saved = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -Raw).Trim() } else { '' }
    # Capture stderr as ordinary output: PowerShell 5 treats native stderr as
    # a terminating error under Stop, including an expected missing module.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $null = & $python -c 'import PIL,numpy,capstone,pefile' 2>&1
    $dependencyStatus = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($dependencyStatus -ne 0 -or $saved -ne $hash) {
        Write-Host 'Installing asset-builder dependencies in .setup-venv (first setup needs internet)...'
        & $python -m pip install --disable-pip-version-check --requirement $requirements | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the connection and run start.cmd again to resume.' }
        Set-Content -LiteralPath $marker -Value $hash -Encoding ASCII
    }
    return $python
}

function Add-AtlasShortcut {
    $desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $shortcutPath = Join-Path $desktop 'ShadowFlare Atlas Core.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($shortcutPath)
    if ((Test-Path -LiteralPath $shortcutPath) -and $link.TargetPath -and $link.TargetPath -ne (Join-Path $launcherRoot 'start.cmd')) {
        $shortcutPath = Join-Path $desktop 'ShadowFlare Atlas Core - Local.lnk'
        $link = $shell.CreateShortcut($shortcutPath)
    }
    $link.TargetPath = Join-Path $launcherRoot 'start.cmd'
    $link.WorkingDirectory = $launcherRoot
    $link.Description = 'ShadowFlare Atlas - items, maps and live controls'
    $link.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"
    $link.Save()
    Write-Host "Desktop shortcut: $shortcutPath"
}

try {
    if (!(Test-Path -LiteralPath (Join-Path $atlasRoot 'live_server.py'))) { throw 'Incomplete Atlas folder. Extract the entire ZIP before running start.cmd.' }
    $atlasPython = Find-AtlasPython
    if (!$atlasPython) {
        if ($CheckOnly) { throw 'Python 3.9+ is not installed.' }
        $atlasPython = Install-AtlasPython
    }
    Write-Host "Python: $atlasPython"
    $builder = Join-Path $launcherRoot 'tools\build_assets.py'
    & $atlasPython -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from build_assets import is_ready; sys.exit(0 if is_ready(sys.argv[2]) else 2)' (Join-Path $launcherRoot 'tools') $atlasRoot
    $ready = $LASTEXITCODE -eq 0
    $needGame = !$ready -or $RebuildAssets -or $SetupOnly -or $GamePath -or $LaunchGame
    $game = if ($needGame -or $CheckOnly) { Get-AtlasGame ($needGame -and !$CheckOnly) } else { $null }
    if ($game) { Write-Host "Game folder: $game" }
    if ($CheckOnly) {
        if (!$ready) { throw 'Asset package is missing. Run start.cmd to generate it from your game files.' }
        Write-Host 'PASS: runtime and local asset package are ready.'
        if (!$game) { Write-Host 'Game folder will be requested when setup or game launch needs it.' }
        exit 0
    }
    if (!$ready -or $RebuildAssets) {
        if (!$game) { throw 'A compatible game folder is required to generate the asset package.' }
        $buildPython = Install-AtlasBuildTools
        Write-Host 'Building your local Atlas from the game. Keep this window open; interrupted steps can resume.'
        & $buildPython $builder --game $game --output $atlasRoot
        if ($LASTEXITCODE -ne 0) { throw 'Asset generation did not finish. Run start.cmd again to resume.' }
    }
    if (!$NoShortcut) { Add-AtlasShortcut }
    if ($Package) {
        & $atlasPython (Join-Path $launcherRoot 'tools\package_local.py')
        if ($LASTEXITCODE -ne 0) { throw 'Local ZIP creation failed.' }
        exit 0
    }
    if ($SetupOnly) { Write-Host 'Setup complete. Open start.cmd or the desktop shortcut.'; exit 0 }
    $liveArguments=@((Join-Path $atlasRoot 'live_server.py'),'--elevate','--display-fix')
    if ($LaunchGame) {
        $liveArguments += @('--launch-game','--game',$game)
        if ($PSBoundParameters.ContainsKey('Width')) { $liveArguments += @('--width',[string]$Width) }
        if ($PSBoundParameters.ContainsKey('Height')) { $liveArguments += @('--height',[string]$Height) }
    }
    & $atlasPython @liveArguments
    exit $LASTEXITCODE
} catch {
    Write-Host "`nShadowFlare Atlas: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
