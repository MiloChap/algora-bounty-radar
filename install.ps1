<#
.SYNOPSIS
    One-shot installer for the Algora bounty radar on Windows.

.DESCRIPTION
    - Locates a real Python interpreter (ignoring the flaky Microsoft Store alias).
    - Securely prompts for a GitHub token, validates it, and stores it as a
      persistent per-user environment variable.
    - Registers a Scheduled Task that runs the radar every 15 minutes.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
#>

$ErrorActionPreference = "Stop"
$TaskName = "AlgoraBountyRadar"
$Root     = $PSScriptRoot
$Script   = Join-Path $Root "algora_radar.py"

Write-Host "`n=== Algora bounty radar - installer ===`n" -ForegroundColor Cyan

# 1. Find a real Python (the WindowsApps alias misbehaves under Task Scheduler) -
function Find-Python {
    $candidates = @()
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try { $candidates += (& py -3 -c "import sys; print(sys.executable)") } catch {}
    }
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try { $candidates += (& python -c "import sys; print(sys.executable)") } catch {}
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c) -and ($c -notlike "*\WindowsApps\*")) { return $c }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    Write-Host "X No real Python interpreter found. Install Python from https://python.org" -ForegroundColor Red
    Write-Host "  (Avoid relying on the Microsoft Store stub - it fails in scheduled tasks.)"
    exit 1
}
# Prefer pythonw.exe (no flashing console window every run)
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
$runExe  = if (Test-Path $pythonw) { $pythonw } else { $python }
Write-Host "[1/4] Python found: $python" -ForegroundColor Green

# 2. GitHub token ----------------------------------------------------------------
Write-Host "`n[2/4] GitHub token"
Write-Host "      Create one at https://github.com/settings/tokens (classic, no scopes needed)."
$existing = [Environment]::GetEnvironmentVariable("GITHUB_TOKEN", "User")
if ($existing) {
    Write-Host "      A GITHUB_TOKEN is already set for your user. Press Enter to keep it,"
    Write-Host "      or paste a new one to replace it."
}
$secure = Read-Host "      Paste your GitHub token (input hidden, Enter to skip)" -AsSecureString
$token  = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

if ($token) {
    # Validate it before saving
    try {
        $null = Invoke-RestMethod -Uri "https://api.github.com/rate_limit" `
            -Headers @{ Authorization = "Bearer $token"; "User-Agent" = "algora-radar" }
        Write-Host "      Token valid." -ForegroundColor Green
    } catch {
        Write-Host "      ! Could not validate the token (continuing anyway)." -ForegroundColor Yellow
    }
    [Environment]::SetEnvironmentVariable("GITHUB_TOKEN", $token, "User")
    $env:GITHUB_TOKEN = $token   # also available in this session
    Write-Host "      Saved as a persistent user environment variable." -ForegroundColor Green
} elseif ($existing) {
    Write-Host "      Keeping the existing token." -ForegroundColor Green
} else {
    Write-Host "      ! No token set - the radar will run but is limited to 60 req/h." -ForegroundColor Yellow
}

# 3. Desktop notifications -------------------------------------------------------
# Required for the scheduled task to alert visibly: it runs windowless (pythonw),
# so console output is invisible and a toast is the only way you'll see a hit.
Write-Host "`n[3/4] Desktop notifications (BurntToast)"
if (Get-Module -ListAvailable -Name BurntToast) {
    Write-Host "      Already installed." -ForegroundColor Green
} else {
    try {
        Install-Module BurntToast -Scope CurrentUser -Force -AllowClobber
        Write-Host "      Installed." -ForegroundColor Green
    } catch {
        Write-Host "      ! Auto-install failed. Run manually: Install-Module BurntToast -Scope CurrentUser" -ForegroundColor Yellow
    }
}

# 4. Register the scheduled task -------------------------------------------------
Write-Host "`n[4/4] Scheduled task '$TaskName' (every 15 minutes)"
try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop } catch {}

$action    = New-ScheduledTaskAction -Execute $runExe -Argument "`"$Script`" --once" -WorkingDirectory $Root
$trigger   = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Algora bounty radar: checks for fresh, unclaimed bounties every 15 minutes." | Out-Null
Write-Host "      Task registered." -ForegroundColor Green

Write-Host "`nDone. The radar will run every 15 minutes." -ForegroundColor Cyan
Write-Host "  - Run now:     python `"$Script`" --once"
Write-Host "  - Manage task: taskschd.msc  (or .\uninstall.ps1 to remove)`n"
