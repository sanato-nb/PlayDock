# PlayDock - Windows release builder
# Usage: double-click 00_BUILD_WINDOWS_EXE.bat (Windows 10/11)
# Build machine needs internet once. Installed apps do NOT require Python.
[CmdletBinding()]
param(
  [switch]$NoLaunch,
  [switch]$SkipTests,
  [switch]$NoWinget
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Step([string]$Message) {
  Write-Host "`n==> $Message" -ForegroundColor Cyan
}
function Assert-ExitCode([string]$Label) {
  if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit code $LASTEXITCODE)" }
}
function Test-Python([string]$Executable, [string[]]$Prefix) {
  try {
    & $Executable @Prefix -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 13) else 1)' 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}
function Find-Python {
  $options = New-Object System.Collections.ArrayList
  if (Get-Command py -ErrorAction SilentlyContinue) {
    [void]$options.Add(@{ Exe='py'; Args=@('-3.12') })
    [void]$options.Add(@{ Exe='py'; Args=@('-3.13') })
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    [void]$options.Add(@{ Exe='python'; Args=@() })
  }
  if (Get-Command python3 -ErrorAction SilentlyContinue) {
    [void]$options.Add(@{ Exe='python3'; Args=@() })
  }
  foreach ($candidate in @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:ProgramFiles 'Python312\python.exe'),
    (Join-Path $env:ProgramFiles 'Python313\python.exe')
  )) {
    if (Test-Path -LiteralPath $candidate) {
      [void]$options.Add(@{ Exe=$candidate; Args=@() })
    }
  }
  foreach ($opt in $options) {
    if (Test-Python ([string]$opt.Exe) ([string[]]$opt.Args)) { return $opt }
  }
  return $null
}
function Run-PyInstaller([string]$Name, [string]$Source, [string[]]$Extra) {
  Step "Building $Name.exe"
  $params = @('--noconfirm', '--clean', '--onefile', '--windowed', '--name', $Name,
              '--icon', 'assets\playdock.ico') + $Extra + @($Source)
  & $script:VenvPython -m PyInstaller @params
  Assert-ExitCode "PyInstaller $Name"
  $built = Join-Path $script:Dist "$Name.exe"
  if (!(Test-Path -LiteralPath $built)) { throw "Missing output file: $built" }
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
  throw 'This build must run on Windows. Use GitHub Actions for a cloud Windows build.'
}
foreach ($required in @('app.py','title_editor.py','setup_wizard.py','requirements.txt',
                       'setup_paths.py','native_caption.py','uninstall_wizard.py','install_management.py','ai_providers.py','game_codes.py','assets\playdock.ico')) {
  if (!(Test-Path -LiteralPath $required)) { throw "Missing source file: $required" }
}

Step 'Looking for Python 3.12 / 3.13'
$python = Find-Python
if ($null -eq $python) {
  if ($NoWinget) { throw 'Python 3.12 or 3.13 not found. Install it from python.org.' }
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($null -eq $winget) {
    throw 'Python 3.12/3.13 missing, and winget is unavailable. Install Python 3.12 from https://www.python.org/downloads/windows/ then rerun.'
  }
  Step 'Installing Python 3.12 (official winget package, current user)'
  Write-Host 'Winget may show a license or confirmation prompt.'
  & winget install --id Python.Python.3.12 --exact --source winget --scope user --accept-source-agreements --accept-package-agreements
  Assert-ExitCode 'winget Python installation'
  $python = Find-Python
  if ($null -eq $python) { throw 'Python was installed but not detected. Open a new terminal and rerun this script.' }
}
$pythonExe = [string]$python.Exe
$pythonArgs = [string[]]$python.Args
Write-Host "Using $pythonExe $($pythonArgs -join ' ')"

$script:VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $script:VenvPython)) {
  Step 'Creating isolated packaging environment'
  & $pythonExe @pythonArgs -m venv (Join-Path $PSScriptRoot '.venv')
  Assert-ExitCode 'Python venv'
}
Step 'Installing Windows dependencies'
& $script:VenvPython -m pip install --upgrade pip
Assert-ExitCode 'pip upgrade'
& $script:VenvPython -m pip install -r requirements.txt 'pyinstaller>=6.10,<7' pytest
Assert-ExitCode 'pip dependencies'

if (!$SkipTests) {
  Step 'Running application tests before release'
  & $script:VenvPython -m pytest -q tests
  Assert-ExitCode 'Unit tests'
}

$script:Dist = Join-Path $PSScriptRoot 'dist'
New-Item -ItemType Directory -Path $script:Dist -Force | Out-Null
Run-PyInstaller 'PlayDock' 'app.py' @('--collect-all','keyring','--collect-all','pyzipper',
                                        '--collect-all','send2trash','--collect-all','ddgs','--hidden-import','rarfile',
                                        '--hidden-import','game_codes',
                                        '--add-data','assets\playdock.ico;assets')
Run-PyInstaller 'PlayDock_TitleEditor' 'title_editor.py' @('--collect-all','keyring','--collect-all','ddgs',
                                    '--hidden-import','game_codes', '--hidden-import','bulk_title_edit',
                                    '--add-data','assets\playdock.ico;assets')
Run-PyInstaller 'PlayDock_Uninstall' 'uninstall_wizard.py' @(
  '--add-data','assets\playdock.ico;assets'
)
Run-PyInstaller 'PlayDock_Setup' 'setup_wizard.py' @(
  '--add-data','assets\playdock.ico;assets',
  '--add-binary','dist\PlayDock.exe;payload',
  '--add-binary','dist\PlayDock_TitleEditor.exe;payload',
  '--add-binary','dist\PlayDock_Uninstall.exe;payload'
)

Step 'Checking Windows uninstaller and embedded installation payload'
& (Join-Path $script:Dist 'PlayDock_Uninstall.exe') --self-test
Assert-ExitCode 'Uninstaller self-test'
& (Join-Path $script:Dist 'PlayDock_Setup.exe') --self-test
Assert-ExitCode 'Installer embedded payload verification'

Step 'Generating checksums and distribution ZIP'
$names = @('PlayDock_Setup.exe','PlayDock.exe','PlayDock_TitleEditor.exe','PlayDock_Uninstall.exe')
$checksums = foreach ($name in $names) {
  $path = Join-Path $script:Dist $name
  $hash = Get-FileHash -Path $path -Algorithm SHA256
  "$($hash.Hash)  $name"
}
$checksumFile = Join-Path $script:Dist 'SHA256SUMS.txt'
$checksums | Set-Content -LiteralPath $checksumFile -Encoding Ascii
$zip = Join-Path $script:Dist 'PlayDock_Windows_Release.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
$inputs = $names | ForEach-Object { Join-Path $script:Dist $_ }
Compress-Archive -Path ($inputs + @($checksumFile)) -DestinationPath $zip -CompressionLevel Optimal -Force
Write-Host ''
Write-Host 'SUCCESS - Windows EXE created:' -ForegroundColor Green
foreach ($name in $names) { Write-Host "  $($script:Dist)\$name" }
Write-Host "  $zip"
Write-Host 'The installer EXE is the only file needed to install on another Windows PC.'
Write-Host 'The EXEs are not code-signed; Windows SmartScreen may warn about unknown publisher.'

if (!$NoLaunch) {
  Step 'Launching the finished Windows installer'
  Start-Process -FilePath (Join-Path $script:Dist 'PlayDock_Setup.exe') -WorkingDirectory $script:Dist
}
