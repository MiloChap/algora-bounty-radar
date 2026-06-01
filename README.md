# Algora Bounty Radar

> Get notified the moment a fresh, unclaimed [Algora](https://algora.io) bounty appears, so you can be *first* instead of 21st.

## Why

Public bounty boards are an efficient market: any bounty that is easy, clear, and
well-paid gets claimed within minutes or buried under 20 competing PRs. The
contributors who actually win are the ones who get there **first** and ask the
maintainer to assign them.

This radar watches GitHub for newly-posted Algora bounties and alerts you only on
the ones still worth grabbing: **unassigned, zero `/attempt`, recent, and on a
real repository.**

## How it works

The Algora bot (`algora-pbc`) comments on every issue that gets a bounty, so this
one GitHub search is effectively the global Algora bounty board:

```
commenter:app/algora-pbc is:issue is:open   (sorted by newest)
```

For each fresh issue, the radar throws away anything that's already assigned, too
old, on a low-star repo, or already has an `/attempt`. Whatever's left is a
genuinely open bounty. It remembers what it has seen in `radar_state.json`, so you
only get alerted on **new** ones.

## Requirements

- Windows + PowerShell
- Python 3.9+
- A GitHub token (classic, **no scopes** needed). This lifts the API limit from 60 to 5000 requests/hour.

## Quick start

```powershell
git clone https://github.com/MiloChap/algora-bounty-radar.git
cd algora-bounty-radar
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

The installer finds your Python, securely asks for your GitHub token, and
registers a Scheduled Task that runs the radar every 15 minutes.

## Manual setup (without the installer)

Prefer to do it by hand? Three steps.

**1. Store your GitHub token** (persists across sessions; `User` is a literal keyword, not your username):

```powershell
[Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "ghp_xxx", "User")
```

**2. Find your real Python** (the Microsoft Store alias misbehaves in scheduled tasks):

```powershell
python -c "import sys; print(sys.executable)"
```

**3a. Either just keep it running** in a terminal:

```powershell
python algora_radar.py            # loop, checks every 15 minutes
```

**3b. Or register a Scheduled Task.** First install BurntToast (see
[Desktop notifications](#desktop-notifications)) so the windowless task can alert you,
then replace `<python>` with the path from step 2 and `<dir>` with this folder
(use `pythonw.exe` to avoid a console window):

```powershell
$action  = New-ScheduledTaskAction -Execute "<python>" -Argument "algora_radar.py --once" -WorkingDirectory "<dir>"
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(2)) -RepetitionInterval (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "AlgoraBountyRadar" -Action $action -Trigger $trigger `
    -Description "Algora bounty radar"
```

## Running it directly

```powershell
$env:GITHUB_TOKEN = "ghp_xxx"     # for the current session only

python algora_radar.py --once     # single pass
python algora_radar.py            # loop
```

The **first** run records all currently-open bounties without alerting. Every run
after that alerts only on new ones.

## Configuration

Edit the constants at the top of [`algora_radar.py`](algora_radar.py):

| Setting | Meaning | Default |
|---|---|---|
| `MIN_STARS` | minimum repo stars (anti-spam) | `5` |
| `MAX_AGE_HOURS` | only alert on bounties created within this window | `72` |
| `MAX_ATTEMPTS` | max existing `/attempt`s allowed (`0` = untouched) | `0` |
| `MIN_AMOUNT` | minimum bounty amount in `$` | `0` |
| `CHECK_EVERY_MIN` | loop interval | `15` |
| `BLOCKLIST` | repos to always skip | — |

## Desktop notifications

Alerts are shown as Windows toasts via the [BurntToast](https://github.com/Windos/BurntToast) module.
The installer sets it up for you. **It is required for the scheduled task**, which
runs windowless, so without it a found bounty produces no visible alert. To install
it by hand:

```powershell
Install-Module BurntToast -Scope CurrentUser
```

(When running the radar directly in a terminal, matches are also printed to the console.)

## Uninstall

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall.ps1
```

## License

[MIT](LICENSE)
