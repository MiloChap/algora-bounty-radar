<#
.SYNOPSIS
    Removes the Algora bounty radar scheduled task (and optionally the token).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
#>

$TaskName = "AlgoraBountyRadar"

Write-Host "`n=== Algora bounty radar - uninstaller ===`n" -ForegroundColor Cyan

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "Scheduled task '$TaskName' removed." -ForegroundColor Green
} catch {
    Write-Host "No scheduled task '$TaskName' found." -ForegroundColor Yellow
}

if ([Environment]::GetEnvironmentVariable("GITHUB_TOKEN", "User")) {
    $answer = Read-Host "Also remove the stored GITHUB_TOKEN? (y/N)"
    if ($answer -match '^[yY]') {
        [Environment]::SetEnvironmentVariable("GITHUB_TOKEN", $null, "User")
        Write-Host "GITHUB_TOKEN removed." -ForegroundColor Green
    } else {
        Write-Host "GITHUB_TOKEN kept." -ForegroundColor Green
    }
}

Write-Host "`nDone.`n" -ForegroundColor Cyan
