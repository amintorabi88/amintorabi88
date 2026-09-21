#!/usr/bin/env python3
"""Update aggregate contribution statistics in a GitHub profile README.

Python standard library only. Set PROFILE_STATS_TOKEN to a personal access token
belonging to the profile owner. Never put the token in this file or the README.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

START = "<!-- STATS:START -->"
END = "<!-- STATS:END -->"
QUERY = """
query($from: DateTime!, $to: DateTime!) {
  viewer {
    login
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      restrictedContributionsCount
    }
  }
}
"""
FIELDS = (
    ("Commits", "totalCommitContributions"),
    ("PRs", "totalPullRequestContributions"),
    ("Reviews", "totalPullRequestReviewContributions"),
    ("Issues", "totalIssueContributions"),
)


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError("GitHub returned a missing or invalid contribution count.")
    return value


def fetch_stats(token, username, now):
    variables = {
        "from": (now - timedelta(days=365)).isoformat().replace("+00:00", "Z"),
        "to": now.isoformat().replace("+00:00", "Z"),
    }
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "aggregate-profile-stats",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as error:
        # Do not log response bodies, request headers, or tokens.
        raise RuntimeError(
            f"GitHub returned HTTP {error.code}. Check the token, its expiration, "
            "and any organization restrictions. The README was not changed."
        ) from None
    except urllib.error.URLError:
        raise RuntimeError("Could not reach GitHub. The README was not changed.") from None
    if payload.get("errors"):
        raise RuntimeError(
            "GitHub could not complete the contribution query. Check token permissions "
            "and organization access. The README was not changed."
        )
    viewer = payload["data"]["viewer"]
    if viewer["login"].lower() != username.lower():
        raise RuntimeError("The stats token must belong to the profile owner.")
    return viewer["contributionsCollection"]


def stats_html(stats, now):
    restricted = count(stats["restrictedContributionsCount"])
    lines = ["<p><strong>Past 365 days</strong></p>"]
    for index, (label, field) in enumerate(FIELDS):
        prefix = "<p>" if index == 0 else ""
        suffix = "</p>" if index == len(FIELDS) - 1 else "<br>"
        lines.append(f"{prefix}{label}: <strong>{count(stats[field]):,}</strong>{suffix}")
    if restricted:
        lines.append(
            "<p><sub>Some private activity may be missing from these totals.</sub></p>"
        )
    # Do not add restricted contributions to commits or other categories.
    lines.append(f"<p><sub>GitHub contribution counts · Updated {now:%Y-%m-%d} UTC</sub></p>")
    return "\n".join(lines)


def replace_stats(readme, block):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one pair of STATS markers.")
    before, remainder = readme.split(START, 1)
    if END not in remainder:
        raise ValueError("README STATS markers are in the wrong order.")
    _, after = remainder.split(END, 1)
    return before + START + "\n" + block + "\n" + END + after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--username", default="amintorabi88")
    args = parser.parse_args()
    token = os.environ.get("PROFILE_STATS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Add the PROFILE_STATS_TOKEN Actions repository secret first.")
    original = args.readme.read_text(encoding="utf-8")
    replace_stats(original, "")  # Validate markers before contacting GitHub.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    stats = fetch_stats(token, args.username, now)
    updated = replace_stats(original, stats_html(stats, now))
    if updated == original:
        print("Contribution statistics are unchanged.")
        return
    temporary = args.readme.with_name(args.readme.name + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    temporary.replace(args.readme)
    print("Updated aggregate contribution statistics. No repository details collected.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Known errors have safe messages. Suppress raw unexpected API payloads.
        if isinstance(error, (RuntimeError, ValueError, OSError)):
            print(str(error), file=sys.stderr)
        else:
            print("The update failed; existing statistics were preserved.", file=sys.stderr)
        sys.exit(1)
