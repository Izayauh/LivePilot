<#
.SYNOPSIS
  Install, update, sign in to, or remove Live Pilot Studio.

.DESCRIPTION
  Double-click install.cmd in this folder. It runs this script and keeps the window open at the end.
  For the options, open PowerShell or Command Prompt in this folder and run:

    .\install.cmd              install (safe to run again: it only fixes what is missing)
    .\install.cmd -Update      pull the latest code, then install again (git copies only)
    .\install.cmd -Login       sign in to Claude (opens Claude in this window; type /login, then /exit)
    .\install.cmd -Uninstall   remove the remote script from Live, the shortcut, the settings, the logs and the backups
    .\install.cmd -NoModel     skip the 2.4 GB speech model download (first start with the mic on fetches it)

  Needs Windows 10 or 11, Python 3.12 or 3.13 (https://www.python.org/downloads/windows/, tick "Add python.exe to PATH"),
  Ableton Live 11 or 12 (any edition), and a Claude account (Pro or Max).
#>
param([switch]$Update, [switch]$Login, [switch]$Uninstall, [switch]$NoModel, [switch]$NoShortcut)

$ErrorActionPreference = "Stop"
# PowerShell 7 also runs on macOS and Linux; Windows PowerShell 5.1 has no $IsWindows, so $env:OS decides there.
if ($IsWindows -eq $false -or $env:OS -ne "Windows_NT") {
    Write-Host "Live Pilot runs on Windows only (Windows 10 or 11). Nothing was installed." -ForegroundColor Red
    exit 1
}
$Root = $PSScriptRoot
$Venv = Join-Path $Root "venv"
$Py = Join-Path $Venv "Scripts\python.exe"
$Pyw = Join-Path $Venv "Scripts\pythonw.exe"
$Shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Live Pilot.lnk"
# Same folders as studio/config.py: LIVEPILOT_HOME moves the settings and the logs together.
$Settings = if ($env:LIVEPILOT_HOME) { $env:LIVEPILOT_HOME } else { Join-Path $env:APPDATA "LivePilot" }
# Logs and the backups scripts/install_remote_script.py makes of a replaced remote script share this folder.
$Logs = if ($env:LIVEPILOT_HOME) { $null } else { Join-Path $env:LOCALAPPDATA "LivePilot" }

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "   $text" -ForegroundColor Green }
function Fail($text) { Write-Host ""; Write-Host "STOPPED: $text" -ForegroundColor Red; exit 1 }

# 3.12 first; 3.13 passes the same tests. Newer versions are untested (the pinned packages may have no wheels yet).
function Find-Python {
    foreach ($cmd in @("py -3.12", "python3.12", "py -3.13", "python3.13", "python")) {
        try {
            $v = & cmd /c "$cmd -c `"import sys; print(sys.version_info[:2] in ((3, 12), (3, 13)))`"" 2>$null
            if ($v -eq "True") { return $cmd }
        } catch {}
    }
    return $null
}

if ($Uninstall) {
    Step "Removing Live Pilot"
    if (Test-Path $Py) {
        $dirs = & $Py -c "from studio import config; print('\n'.join(str(p) for p in config.installed_remote_scripts()))"
        foreach ($d in ($dirs -split "`n" | Where-Object { $_.Trim() })) {
            Remove-Item -Recurse -Force $d.Trim(); Ok "removed $($d.Trim())"
            # Older installers left their backup inside Live's folder, where Live lists it as a second control surface.
            $bak = Join-Path (Split-Path $d.Trim()) "LivePilot.bak"
            if (Test-Path $bak) { Remove-Item -Recurse -Force $bak }
        }
    } else {
        Write-Host "   This folder has no Python environment, so I cannot look up where the remote script went." -ForegroundColor Yellow
        Write-Host "   If Live still lists LivePilot, delete the LivePilot folder inside Live's MIDI Remote Scripts folder." -ForegroundColor Yellow
    }
    # Only the shortcut this folder made: another Live Pilot folder on this PC keeps its own.
    if ((Test-Path $Shortcut) -and ((New-Object -ComObject WScript.Shell).CreateShortcut($Shortcut).TargetPath -eq $Pyw)) {
        Remove-Item $Shortcut; Ok "removed the desktop shortcut"
    }
    if (Test-Path $Settings) { Remove-Item -Recurse -Force $Settings; Ok "removed settings in $Settings" }
    if ($Logs -and (Test-Path $Logs)) { Remove-Item -Recurse -Force $Logs; Ok "removed logs and remote script backups in $Logs" }
    Write-Host ""
    Write-Host "Done. Delete this folder to remove the code and the Python environment. Your Claude sign-in and the"
    Write-Host "speech model in $env:USERPROFILE\.cache\huggingface are untouched (other apps may use them)."
    exit 0
}

if ($Login) {
    Step "Signing in to Claude"
    if (-not (Test-Path $Py)) { Fail "Install first: double-click install.cmd in this folder." }
    $cli = & $Py -c "import claude_agent_sdk, pathlib; print(pathlib.Path(claude_agent_sdk.__file__).parent / '_bundled' / 'claude.exe')"
    Write-Host "   Claude opens below. Type /login and follow the link, then type /exit to come back here."
    & $cli
    $ok = & $Py -c "from studio import config; print(config.claude_signed_in())"
    if ($ok -eq "True") { Ok "signed in" } else { Fail "No sign-in found. Run .\install.cmd -Login again." }
    exit 0
}

if ($Update) {
    Step "Getting the latest code"
    if (-not (Test-Path (Join-Path $Root ".git"))) {
        Fail ("This folder came from a zip, so it cannot update itself. Download the newest LivePilot zip from the " +
              "Releases page, unzip it to a new folder, double-click install.cmd there, then delete this folder. " +
              "Your settings are kept.")
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git is not installed. Download the newest zip instead and run install.cmd from it." }
    & git -C $Root pull --ff-only
    if ($LASTEXITCODE -ne 0) { Fail "git pull failed (see above). Fix it, or download a fresh zip." }
}

Step "Python 3.12 or 3.13"
if (Test-Path $Py) {
    Ok "using the Python environment in $Venv"
} else {
    $sys = Find-Python
    if (-not $sys) { Fail "Python 3.12 or 3.13 was not found (3.14 and newer are not supported yet). Install Python 3.12 or 3.13 from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'), then run this again." }
    & cmd /c "$sys -m venv `"$Venv`""
    if (-not (Test-Path $Py)) { Fail "Could not create the Python environment in $Venv." }
    Ok "created $Venv"
}

Step "Python packages (a few minutes the first time)"
& $Py -m pip install --quiet --upgrade pip
# constraints.txt pins every package to the version Live Pilot is tested with.
& $Py -m pip install --quiet -r (Join-Path $Root "requirements-studio.txt") -c (Join-Path $Root "constraints.txt")
if ($LASTEXITCODE -ne 0) { Fail "pip could not install the packages. Check your internet connection and run this again." }
Ok "installed"

Step "LivePilot remote script into Ableton Live"
# stdout only: anything Python prints to stderr shows on screen instead of breaking the JSON
# (in Windows PowerShell, 2>&1 also turns any stderr line into a red NativeCommandError that stops the script).
$out = & $Py (Join-Path $Root "scripts\install_remote_script.py")
try { $result = $out | Out-String | ConvertFrom-Json } catch { $result = $null }
if (-not $result) { Fail "Could not install the remote script (the error is above). Run this again; if it repeats, send that text to whoever gave you Live Pilot." }
if (-not $result.success) { Fail $result.message }
foreach ($i in $result.installed) {
    $state = if ($i.fresh) { "new" } elseif ($i.changed.Count) { "updated" } else { "up to date" }
    Ok "$($i.dir) ($($i.files) files, $state)"
}
Write-Host "   $($result.message)"

Step "Claude sign-in"
$signed = & $Py -c "from studio import config; print(config.claude_signed_in())"
if ($signed -eq "True") { Ok "signed in" } else {
    Write-Host "   Not signed in yet. Claude opens below: type /login and follow the link, then type /exit." -ForegroundColor Yellow
    $cli = & $Py -c "import claude_agent_sdk, pathlib; print(pathlib.Path(claude_agent_sdk.__file__).parent / '_bundled' / 'claude.exe')"
    & $cli
    $signed = & $Py -c "from studio import config; print(config.claude_signed_in())"
    if ($signed -eq "True") { Ok "signed in" } else { Write-Host "   Still not signed in. Run .\install.cmd -Login later." -ForegroundColor Yellow }
}

if (-not $NoModel) {
    Step "Speech model (2.4 GB, once)"
    $cached = & $Py -c "from studio import config; print(config.asr_model_cached())"
    if ($cached -eq "True") { Ok "already downloaded" } else {
        & $Py -c "import onnx_asr; onnx_asr.load_vad('silero'); onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v2'); print('ok')"
        if ($LASTEXITCODE -ne 0) { Write-Host "   Download failed; Studio will try again on first start." -ForegroundColor Yellow } else { Ok "downloaded" }
    }
}

Step "Your settings ($Settings\config.json)"
if (-not (Test-Path (Join-Path $Settings "config.json"))) {
    $name = Read-Host "   What should Studio call you? (Enter to skip)"
    $artist = Read-Host "   Artist name, if any (Enter to skip)"
    # Passed through the environment, so quotes or backslashes in a name cannot break the Python line.
    $env:LP_NAME = "$name"; $env:LP_ARTIST = "$artist"
    & $Py -c "import os; from studio import config; c = config.load(); c['name'] = os.environ.get('LP_NAME', '').strip(); c['artist_name'] = os.environ.get('LP_ARTIST', '').strip(); config.save(c)"
    if ($LASTEXITCODE -ne 0) { Fail "Could not write $Settings\config.json (the error is above)." }
    Ok "saved"
} else { Ok "kept" }

if (-not $NoShortcut) {
    Step "Desktop shortcut"
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($Shortcut)
    $s.TargetPath = $Pyw
    $s.Arguments = "-m studio"
    $s.WorkingDirectory = $Root
    $s.IconLocation = (Join-Path $Root "studio\static\icon.ico") + ",0"
    $s.Description = "Live Pilot Studio: talk to Ableton Live"
    $s.WindowStyle = 7
    $s.Save()
    if (Test-Path $Shortcut) { Ok "Live Pilot is on your desktop" } else { Write-Host "   Could not write the shortcut; start with: $Pyw -m studio" -ForegroundColor Yellow }
}

Step "Checking everything"
Write-Host "   (The 'Ableton Live is answering' line says FIX while Live is closed. That is expected.)"
& $Py -m studio --check
Write-Host ""
Write-Host "Install finished. Open Ableton Live, enable LivePilot as a Control Surface once (Options > Preferences >"
Write-Host "Link, Tempo & MIDI), then double-click Live Pilot on your desktop and talk." -ForegroundColor Green
