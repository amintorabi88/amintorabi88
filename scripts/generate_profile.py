"""
Generate dark_mode.svg and light_mode.svg with live GitHub stats.

Designed for the GitHub profile:
https://github.com/amintorabi88

Runs from GitHub Actions.
Stdlib only. No third-party dependencies.
"""

import html
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


USER = "amintorabi88"

# GitHub account creation year, verified against the public profile API.
JOINED_YEAR = 2022

# Width of the information column, measured in monospace characters.
W = 58


# ---------------------------------------------------------------------------
# ASCII ART
# ---------------------------------------------------------------------------
#
# For now this is a clean ML / terminal-style graphic.
#
# Later we can replace this with an ASCII version of your portrait if you want.
#

ART = r"""
               ╭────────────────────╮
               │   MACHINE LEARNING │
               ╰─────────┬──────────╯
                         │
                  ┌──────▼──────┐
                  │    DATA     │
                  │   SCIENCE   │
                  └──────┬──────┘
                         │
              ┌──────────▼──────────┐
              │                     │
              │      ◉       ◉      │
              │                     │
              │      NEURAL         │
              │      NETWORK        │
              │                     │
              │    ◉ ── ◉ ── ◉     │
              │     ╲   │   ╱       │
              │      ╲  │  ╱        │
              │       ╲ │ ╱         │
              │        ◉            │
              │                     │
              └──────────┬──────────┘
                         │
                  ┌──────▼──────┐
                  │ PREDICTION  │
                  └─────────────┘

                    AMIN TORABI
                 ML / DATA SCIENCE
"""


# ---------------------------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------------------------
#
# GITHUB_TOKEN:
# Automatically supplied by GitHub Actions.
#
# ACCESS_TOKEN:
# Optional Personal Access Token stored as a repository secret.
#
# ACCESS_TOKEN lets the workflow see private repositories where the token has
# permission. Without it, the script still works but some private activity may
# not be visible.
#

TOKEN = (
    os.environ.get("GITHUB_TOKEN")
    or os.environ.get("ACCESS_TOKEN")
    or ""
)

PRIV_TOKEN = os.environ.get("ACCESS_TOKEN") or TOKEN


# ---------------------------------------------------------------------------
# GITHUB API HELPERS
# ---------------------------------------------------------------------------


def gh(url, payload=None, token=None):
    """Call the GitHub API."""

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-readme",
    }

    auth_token = token or TOKEN

    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload else None,
        headers=headers,
    )

    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read()

        if not body:
            return response.status, {}

        return response.status, json.loads(body)


def graphql(query, variables=None, token=None):
    """Run a GitHub GraphQL query."""

    _, response = gh(
        "https://api.github.com/graphql",
        {
            "query": query,
            "variables": variables or {},
        },
        token,
    )

    if response.get("errors"):
        raise RuntimeError(response["errors"])

    return response["data"]


# ---------------------------------------------------------------------------
# GITHUB STATISTICS
# ---------------------------------------------------------------------------


def fetch_public_stats():
    """Render public REST counts without inventing token-only statistics."""
    _, user = gh(f"https://api.github.com/users/{USER}")
    repos = []
    page = 1
    while True:
        _, batch = gh(
            f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}"
        )
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return {
        "repos": user["public_repos"], "followers": user["followers"],
        "stars": sum(repo["stargazers_count"] for repo in repos),
        "contributed": None, "commits": None,
        "loc": None, "loc_add": None, "loc_del": None,
    }


def fetch_stats():
    """Fetch GitHub statistics for the profile."""

    current_year = datetime.now(timezone.utc).year

    contribution_queries = "\n".join(
        (
            f'y{year}: contributionsCollection('
            f'from: "{year}-01-01T00:00:00Z", '
            f'to: "{year}-12-31T23:59:59Z") '
            "{ "
            "totalCommitContributions "
            "restrictedContributionsCount "
            "}"
        )
        for year in range(JOINED_YEAR, current_year + 1)
    )

    contribution_data = graphql(
        f"""
        query {{
            user(login: "{USER}") {{
                {contribution_queries}
            }}
        }}
        """
    )["user"]

    commits = sum(
        value["totalCommitContributions"]
        for value in contribution_data.values()
    )

    user = graphql(
        f"""
        query {{
            user(login: "{USER}") {{
                id

                followers {{
                    totalCount
                }}

                repositories(
                    first: 100,
                    ownerAffiliations: OWNER
                ) {{
                    totalCount

                    nodes {{
                        name
                        stargazerCount
                        isFork
                    }}
                }}

                repositoriesContributedTo(
                    first: 1,
                    contributionTypes: [
                        COMMIT,
                        PULL_REQUEST,
                        REPOSITORY
                    ]
                ) {{
                    totalCount
                }}
            }}
        }}
        """,
        token=PRIV_TOKEN,
    )["user"]

    repos = user["repositories"]["nodes"]

    stats = {
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": sum(
            repo["stargazerCount"]
            for repo in repos
        ),
        "commits": commits,
    }

    owned_non_fork_repos = [
        repo["name"]
        for repo in repos
        if not repo["isFork"]
    ]

    stats.update(
        fetch_loc(
            owned_non_fork_repos,
            user["id"],
        )
    )

    return stats


# ---------------------------------------------------------------------------
# LINES OF CODE
# ---------------------------------------------------------------------------
#
# GitHub's REST contributor statistics endpoint often responds with HTTP 202
# while stats are being generated.
#
# Instead, walk Amin's commits on each repository's default branch using
# GraphQL and sum additions / deletions.
#

LOC_QUERY = """
query(
    $owner: String!,
    $name: String!,
    $id: ID!,
    $cursor: String
) {
    repository(
        owner: $owner,
        name: $name
    ) {
        defaultBranchRef {
            target {
                ... on Commit {
                    history(
                        first: 100,
                        author: {id: $id},
                        after: $cursor
                    ) {
                        pageInfo {
                            hasNextPage
                            endCursor
                        }

                        nodes {
                            additions
                            deletions
                        }
                    }
                }
            }
        }
    }
}
"""


def fetch_loc(repo_names, user_id):
    """Calculate additions, deletions, and approximate net LOC."""

    additions = 0
    deletions = 0

    for repo_name in repo_names:
        cursor = None

        try:
            while True:
                data = graphql(
                    LOC_QUERY,
                    {
                        "owner": USER,
                        "name": repo_name,
                        "id": user_id,
                        "cursor": cursor,
                    },
                    token=PRIV_TOKEN,
                )

                repo = data["repository"]

                if repo is None:
                    break

                ref = repo["defaultBranchRef"]

                if ref is None:
                    # Empty repository.
                    break

                history = ref["target"]["history"]

                additions += sum(
                    commit["additions"]
                    for commit in history["nodes"]
                )

                deletions += sum(
                    commit["deletions"]
                    for commit in history["nodes"]
                )

                page_info = history["pageInfo"]

                if not page_info["hasNextPage"]:
                    break

                cursor = page_info["endCursor"]

        except Exception as exc:
            # One broken/private/unavailable repository should not prevent
            # generation of the entire profile.
            print(f"LOC error for {repo_name}: {exc}")

    return {
        "loc_add": additions,
        "loc_del": deletions,
        "loc": additions - deletions,
    }


# ---------------------------------------------------------------------------
# COLOR THEMES
# ---------------------------------------------------------------------------


PALETTES = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "art": "#8b949e",
        "h": "#58a6ff",
        "k": "#ffa657",
        "v": "#c9d1d9",
        "d": "#484f58",
        "g": "#3fb950",
        "r": "#f85149",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "art": "#57606a",
        "h": "#0969da",
        "k": "#953800",
        "v": "#24292f",
        "d": "#afb8c1",
        "g": "#1a7f37",
        "r": "#cf222e",
    },
}


# ---------------------------------------------------------------------------
# TEXT FORMATTING
# ---------------------------------------------------------------------------


def kv(key, value, width=W):
    """Create a key/value line with dotted padding."""

    value = str(value)

    dots = "." * max(
        width - len(key) - len(value) - 3,
        1,
    )

    return [
        (f"{key}: ", "k"),
        (dots + " ", "d"),
        (value, "v"),
    ]


def kv2(key1, value1, key2, value2):
    """Render two statistics on one line."""

    left = kv(
        key1,
        value1,
        31,
    )

    return (
        left
        + [(" | ", "d")]
        + kv(
            key2,
            value2,
            24,
        )
    )


def rule(title=""):
    """Create a horizontal section divider."""

    label = f"─ {title} " if title else ""

    return [
        (label, "h"),
        (
            "─" * max(W - len(label), 0),
            "d",
        ),
    ]


def info_lines(stats):
    """Create the information shown on the right side."""

    n = lambda value: "N/A" if value is None else f"{value:,}"

    return [
        [
            (
                f"{USER}@github ",
                "h",
            ),
            (
                "─" * max(
                    W - len(USER) - 8,
                    0,
                ),
                "d",
            ),
        ],

        [],

        kv(
            "OS",
            "macOS",
        ),

        kv(
            "Location",
            "Philadelphia, PA",
        ),

        kv(
            "Host",
            "FMC Corporation",
        ),

        kv(
            "Kernel",
            "Data Scientist / ML Engineer",
        ),

        kv(
            "IDE",
            "PyCharm, VS Code, Databricks",
        ),

        [],

        rule("Stack"),

        kv(
            "Languages",
            "Python, SQL",
        ),

        kv(
            "ML.CV",
            "PyTorch, YOLO, RF-DETR",
        ),

        kv(
            "MLOps",
            "MLflow, Model Serving",
        ),

        kv(
            "Data",
            "Spark, Delta Lake, PostgreSQL",
        ),

        kv(
            "Cloud",
            "Azure, Databricks",
        ),

        [],

        rule("Focus"),

        kv(
            "Computer Vision",
            "Object Detection",
        ),

        kv(
            "Machine Learning",
            "Training + Deployment",
        ),

        kv(
            "Current Interest",
            "AI / ML Platforms",
        ),

        [],

        rule("GitHub Stats"),

        kv2(
            "Repos",
            f"{n(stats['repos'])} "
            f"{{Contributed: {n(stats['contributed'])}}}",
            "Stars",
            n(stats["stars"]),
        ),

        kv2(
            "Commits",
            n(stats["commits"]),
            "Followers",
            n(stats["followers"]),
        ),

        [
            (
                "Net lines changed: ",
                "k",
            ),
            (
                n(stats["loc"]),
                "v",
            ),
            (
                " ( ",
                "d",
            ),
            (
                n(stats["loc_add"]) + "++",
                "g",
            ),
            (
                ", ",
                "d",
            ),
            (
                n(stats["loc_del"]) + "--",
                "r",
            ),
            (
                " )",
                "d",
            ),
        ],
    ]


# ---------------------------------------------------------------------------
# SVG GENERATION
# ---------------------------------------------------------------------------


def render(mode, stats):
    """Generate an SVG for light or dark mode."""

    palette = PALETTES[mode]

    output = [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="1000" '
            'height="560" '
            'viewBox="0 0 1000 560" '
            'font-family="Consolas, Menlo, Monaco, monospace" '
            'font-size="13px">'
        ),
        (
            '<rect '
            'x="0.5" '
            'y="0.5" '
            'width="999" '
            'height="559" '
            'rx="12" '
            f'fill="{palette["bg"]}" '
            f'stroke="{palette["border"]}"'
            '/>'
        ),
    ]

    # Left-side art.
    for index, line in enumerate(
        ART.strip("\n").split("\n")
    ):
        y = 45 + index * 16

        output.append(
            (
                '<text '
                'x="30" '
                f'y="{y}" '
                f'fill="{palette["art"]}" '
                'xml:space="preserve">'
                f"{html.escape(line)}"
                "</text>"
            )
        )

    # Right-side information.
    for index, segments in enumerate(
        info_lines(stats)
    ):
        if not segments:
            continue

        spans = "".join(
            (
                f'<tspan fill="{palette[color]}">'
                f"{html.escape(text)}"
                "</tspan>"
            )
            for text, color in segments
        )

        y = 43 + index * 21

        output.append(
            (
                '<text '
                'x="440" '
                f'y="{y}" '
                'xml:space="preserve">'
                f"{spans}"
                "</text>"
            )
        )

    output.append("</svg>")

    return "\n".join(output)


# ---------------------------------------------------------------------------
# SELF CHECKS
# ---------------------------------------------------------------------------


def selfcheck():
    """Basic checks to catch formatting bugs."""

    sample = kv(
        "OS",
        "macOS",
    )

    text = "".join(
        value
        for value, _ in sample
    )

    assert len(text) == W

    assert "dark" in PALETTES
    assert "light" in PALETTES

    assert USER


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main():
    """Generate both SVG profile cards."""

    selfcheck()


    print(
        f"Fetching GitHub statistics for {USER}..."
    )

    stats = fetch_stats() if TOKEN else fetch_public_stats()

    print(
        "Stats:",
        json.dumps(
            stats,
            indent=2,
        ),
    )

    for mode in PALETTES:
        filename = Path(__file__).resolve().parents[1] / f"{mode}_mode.svg"

        svg = render(
            mode,
            stats,
        )

        with open(
            filename,
            "w",
            encoding="utf-8",
        ) as file:
            file.write(svg)

        print(
            f"Wrote {filename}"
        )


if __name__ == "__main__":
    main()
