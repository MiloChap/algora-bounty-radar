#!/usr/bin/env python3
"""
Algora bounty radar.

Detects freshly-published Algora bounties on GitHub (via the algora-pbc bot)
that are still UP FOR GRABS: unassigned, zero `/attempt`, recent, and on a
serious repo (anti-spam filter by star count).

Only alerts on NEW bounties (state persisted in radar_state.json), so you can be
among the first to `/attempt` and ask the maintainer to assign you.

Usage:
    python algora_radar.py            # loop, checks every CHECK_EVERY_MIN minutes
    python algora_radar.py --once     # single pass (ideal for Windows Task Scheduler)

Tip: set a GitHub token to go from 60 to 5000 requests/hour:
    PowerShell: $env:GITHUB_TOKEN = "ghp_xxx"   (classic token, no scopes needed for public data)
"""

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- configuration
MIN_STARS = 5            # repos below this are ignored (anti-spam / personal repos)
MAX_AGE_HOURS = 72       # only consider bounties created within this window
MAX_ATTEMPTS = 0         # 0 = only bounties nobody has /attempt-ed yet
MIN_AMOUNT = 0           # minimum amount in $ (0 = no filter)
CHECK_EVERY_MIN = 15     # loop interval (when not using --once)
PER_PAGE = 50            # number of recent issues scanned per pass

# Repos known to be spam / bounty-farming playgrounds: skipped outright
BLOCKLIST = {
    "UnsafeLabs/Bounty-Hunters",
    "SecureBananaLabs/bug-bounty",
    "UnsafeLabs/Coolify-Rust-v4",
}

STATE_FILE = pathlib.Path(__file__).with_name("radar_state.json")
TOKEN = os.environ.get("GITHUB_TOKEN")
SESSION_STARS: dict[str, int] = {}   # per-run cache of repo star counts


# ---------------------------------------------------------------- API access
def api(url: str):
    headers = {"User-Agent": "algora-radar", "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            reset = e.headers.get("X-RateLimit-Reset")
            when = ""
            if reset:
                when = " (resets ~" + dt.datetime.fromtimestamp(int(reset)).strftime("%H:%M") + ")"
            print(f"  ! GitHub rate limit hit{when}. "
                  f"Set GITHUB_TOKEN for 5000 req/h.", file=sys.stderr)
        else:
            print(f"  ! API error {e.code} on {url}", file=sys.stderr)
        raise


def search_recent_bounties():
    # The algora-pbc bot comments on every bountied issue, so "issues this bot
    # commented on" is effectively the global Algora bounty board.
    q = "commenter:app/algora-pbc is:issue is:open"
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": q, "per_page": PER_PAGE, "sort": "created", "order": "desc"})
    return api(url).get("items", [])


def repo_stars(repo: str) -> int:
    if repo in SESSION_STARS:
        return SESSION_STARS[repo]
    try:
        stars = api(f"https://api.github.com/repos/{repo}").get("stargazers_count", 0)
    except Exception:
        stars = 0
    SESSION_STARS[repo] = stars
    return stars


def bounty_meta(repo: str, number: int):
    """Return (amount_str, amount_int, attempt_count) parsed from the bot comment."""
    try:
        comments = api(f"https://api.github.com/repos/{repo}/issues/{number}/comments?per_page=100")
    except Exception:
        return "?", 0, 0
    amount_s, amount_i, attempts = "?", 0, 0
    for c in comments:
        if c["user"]["login"].startswith("algora"):
            m = re.search(r"\$[\d,]+", c["body"])
            if m:
                amount_s = m.group(0)
                amount_i = int(amount_s.replace("$", "").replace(",", ""))
            # attempt table rows look like: "| @user | date | ... |"
            attempts = len(re.findall(r"@[\w-]+\s*\|", c["body"]))
    return amount_s, amount_i, attempts


# ---------------------------------------------------------------- state / notify
def load_seen() -> set[str]:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen: set[str]):
    STATE_FILE.write_text(json.dumps(sorted(seen)), encoding="utf-8")


def notify(title: str, message: str, url: str = ""):
    """Windows toast (via BurntToast if installed); silently skipped otherwise.

    If `url` is given, clicking the toast opens it in the default browser.
    """
    def esc(s: str) -> str:                       # escape ' for PowerShell single-quoted strings
        return s.replace("'", "''")
    # A protocol button is encoded in the toast itself, so it still opens the URL
    # after this fire-and-forget process exits (unlike a scriptblock action).
    if url:
        button = f"$b = New-BTButton -Content 'Open issue' -Arguments '{esc(url)}'; "
        notif = f"New-BurntToastNotification -Text '{esc(title)}', '{esc(message)}' -Button $b"
    else:
        button = ""
        notif = f"New-BurntToastNotification -Text '{esc(title)}', '{esc(message)}'"
    command = f"if (Get-Module -ListAvailable -Name BurntToast) {{ {button}{notif} }}"
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", command],
                       capture_output=True, timeout=15)
    except Exception:
        pass


# ---------------------------------------------------------------- logic
def hours_since(iso: str) -> float:
    created = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - created).total_seconds() / 3600


def scan(seen: set[str]):
    fresh_hits = []
    for it in search_recent_bounties():
        repo = it["repository_url"].split("/repos/")[1]
        number = it["number"]
        key = f"{repo}#{number}"
        if key in seen or repo in BLOCKLIST:
            continue
        if it["assignees"]:                       # already assigned -> not free
            continue
        age = hours_since(it["created_at"])
        if age > MAX_AGE_HOURS:                    # too old
            seen.add(key)                          # mark so we don't recheck it
            continue
        if repo_stars(repo) < MIN_STARS:           # not a serious repo
            seen.add(key)
            continue
        amount_s, amount_i, attempts = bounty_meta(repo, number)
        if attempts > MAX_ATTEMPTS or amount_i < MIN_AMOUNT:
            seen.add(key)
            continue
        seen.add(key)
        fresh_hits.append({
            "repo": repo, "number": number, "title": it["title"],
            "amount": amount_s, "age_h": round(age, 1),
            "stars": SESSION_STARS.get(repo, 0), "url": it["html_url"],
        })
    return fresh_hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="run a single pass then exit")
    args = ap.parse_args()

    while True:
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        seen = load_seen()
        first_run = len(seen) == 0
        failed = False
        try:
            hits = scan(seen)
        except Exception:
            hits, failed = [], True                # error already logged (e.g. rate limit)
        # Don't freeze an incomplete baseline: if the very first pass fails,
        # skip saving so we retry cleanly next time.
        if not (first_run and failed):
            save_seen(seen)

        if first_run and failed:
            print(f"[{stamp}] Incomplete pass (API). No baseline saved, will retry. "
                  f"Set GITHUB_TOKEN to avoid this.")
        elif first_run:
            print(f"[{stamp}] First run: memorized {len(seen)} existing bounties. "
                  f"From now on, only NEW ones will trigger alerts.")
        elif hits:
            print(f"[{stamp}] {len(hits)} NEW free bounty(ies)!")
            for h in hits:
                print(f"   {h['amount']:>6}  {h['repo']}#{h['number']}  "
                      f"({h['age_h']}h, {h['stars']}*)  {h['title'][:55]}")
                print(f"          {h['url']}")
            top = hits[0]
            notify(f"Free bounty {top['amount']}",
                   f"{top['repo']}#{top['number']} - {top['title'][:60]}",
                   top["url"])
        else:
            print(f"[{stamp}] Nothing new.")

        if args.once:
            break
        time.sleep(CHECK_EVERY_MIN * 60)


if __name__ == "__main__":
    main()
