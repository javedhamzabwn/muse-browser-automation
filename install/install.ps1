<#
.SYNOPSIS
  Idempotent installer for muse-browser-automation (Muse Browser Control).

.DESCRIPTION
  Deploys the extension + loopback daemon + cookie exporter to
  $env:USERPROFILE\muse-browser-mcp, registers daemon autostart on login,
  and schedules the daily cookie export. Safe to re-run.

  After this script finishes you MUST do the manual Chrome steps it prints
  (loading an unpacked extension cannot be scripted).
#>
$ErrorActionPreference = "Stop"

$RepoDir  = Split-Path -Parent $PSScriptRoot   # repo root (this script lives in install/)
$Target   = Join-Path $env:USERPROFILE "muse-browser-mcp"
$DaemonPy = Join-Path $Target "daemon\simpled.py"
$VbsSrc   = Join-Path $RepoDir "install\StartMuseMCP.vbs"
$Startup  = [IO.Path]::Combine($env:APPDATA, "Microsoft\Windows\Start Menu\Programs\Startup")
$TaskName = "MuseCookieExport"

Write-Host "== muse-browser-automation installer ==" -ForegroundColor Cyan
Write-Host "Repo:   $RepoDir"
Write-Host "Target: $Target"
Write-Host ""

# --- 1. Python 3.10+ on PATH ------------------------------------------------
try {
  $pyVer = & python --version 2>&1
} catch {
  Write-Host "ERROR: Python 3.10+ must be installed and on PATH." -ForegroundColor Red
  Write-Host "Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then re-run this script."
  exit 1
}
if ($pyVer -notmatch "Python (\d+)\.(\d+)") { Write-Host "ERROR: could not parse python version: $pyVer" -ForegroundColor Red; exit 1 }
$major, $minor = [int]$Matches[1], [int]$Matches[2]
if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
  Write-Host "ERROR: found $pyVer — need Python 3.10 or newer." -ForegroundColor Red
  exit 1
}
Write-Host "[ok] $pyVer"

# --- 2. Copy repo files ------------------------------------------------------
foreach ($dir in @("core", "extension", "daemon", "tools", "obscura")) {
  $src = Join-Path $RepoDir $dir
  $dst = Join-Path $Target $dir
  if (-not (Test-Path $src)) { Write-Host "ERROR: missing in repo: $src" -ForegroundColor Red; exit 1 }
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  Copy-Item -Path (Join-Path $src "*") -Destination $dst -Recurse -Force
  Write-Host "[ok] copied $dir -> $dst"
}
Copy-Item -Path (Join-Path $RepoDir "cli.py") -Destination (Join-Path $Target "cli.py") -Force
Write-Host "[ok] copied cli.py -> $Target"

# --- 3. Python deps & Engines ------------------------------------------------
Write-Host "Installing Python dependencies: websockets playwright aiohttp ..."
& python -m pip install --quiet websockets playwright aiohttp
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: pip install failed." -ForegroundColor Red; exit 1 }
Write-Host "[ok] websockets, playwright & aiohttp"

Write-Host "Ensuring Playwright Chromium is installed..."
& python -m playwright install chromium
Write-Host "[ok] Playwright Chromium"

Write-Host "Auto-provisioning Obscura stealth engine..."
try {
  & python -c "from core.obscura_downloader import ensure_obscura_installed; ensure_obscura_installed()"
  Write-Host "[ok] Obscura binary verified"
} catch {
  Write-Host "WARN: Obscura download error: $_" -ForegroundColor Yellow
}

# --- 4. Autostart on login ----------------------------------------------------
Copy-Item -Path $VbsSrc -Destination (Join-Path $Startup "StartMuseMCP.vbs") -Force
Write-Host "[ok] daemon autostart registered (shell:startup -> StartMuseMCP.vbs)"

# --- 5. Start the daemon now (if not already listening) -----------------------
$listening = $false
try {
  $r = Invoke-RestMethod -Uri "http://127.0.0.1:18010/tool" -Method Post `
       -Body '{"tool":"ping","args":{}}' -ContentType "application/json" -TimeoutSec 5
  $listening = $true
} catch { }
if ($listening) {
  Write-Host "[ok] daemon already running on 127.0.0.1:18010"
} else {
  Start-Process -FilePath "pythonw.exe" -ArgumentList "`"$DaemonPy`"" -WindowStyle Hidden
  Start-Sleep -Seconds 3
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:18010/tool" -Method Post `
      -Body '{"tool":"ping","args":{}}' -ContentType "application/json" -TimeoutSec 5 | Out-Null
    Write-Host "[ok] daemon started on 127.0.0.1:18010"
  } catch {
    Write-Host "WARN: daemon did not answer on 127.0.0.1:18010 yet — it may still be starting." -ForegroundColor Yellow
  }
}

# --- 6. Daily cookie-export scheduled task (04:00) ----------------------------
$Exporter = Join-Path $Target "tools\export_cookies.py"
$action  = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument "`"$Exporter`""
$trigger = New-ScheduledTaskTrigger -Daily -At 04:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
try {
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Daily Chrome cookie export (Netscape format) via Muse Browser Control" -Force | Out-Null
  Write-Host "[ok] scheduled task '$TaskName' daily at 04:00"
} catch {
  Write-Host "WARN: could not register scheduled task '$TaskName': $_" -ForegroundColor Yellow
  Write-Host "      Run this script as Administrator to enable the daily cookie export."
}

# --- 7. Manual Chrome steps (cannot be scripted) -------------------------------
Write-Host ""
Write-Host "================ MANUAL STEPS (in Chrome, ~1 minute) ================" -ForegroundColor Cyan
Write-Host "1. Open chrome://extensions"
Write-Host "2. Enable 'Developer mode' (top right)"
Write-Host "3. Click 'Load unpacked' and select:"
Write-Host "     $Target\extension"
Write-Host "4. Confirm the 'Muse Browser Control' extension is enabled."
Write-Host "====================================================================="
Write-Host ""

# --- 8. Verification -----------------------------------------------------------
Write-Host "Verifying daemon..."
try {
  $resp = Invoke-RestMethod -Uri "http://127.0.0.1:18010/tool" -Method Post `
    -Body '{"tool":"ping","args":{}}' -ContentType "application/json" -TimeoutSec 5
  Write-Host "[ok] daemon answered: $($resp | ConvertTo-Json -Compress)"
} catch {
  Write-Host "WARN: http://127.0.0.1:18010/tool did not answer. Check that the daemon is running, then retry." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "================ MUSE BLAZING FAST 3.0 READY ================" -ForegroundColor Green
Write-Host "Real-Time Dashboard: http://127.0.0.1:18010/dashboard"
Write-Host "Unified CLI        : python $Target\cli.py status"
Write-Host "Done. Complete the manual Chrome steps above, then AI agents can drive this PC's browser with universal zero-shot accuracy."
Write-Host "=============================================================="
