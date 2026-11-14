#!/usr/bin/env python3
"""Render the profile widgets (stats.svg, languages.svg, hero.svg) and the README's recent-repos list.

Stdlib only. Reads public data through the GitHub GraphQL API:

    GITHUB_TOKEN=... python3 scripts/render.py --login rafiistcool --out dist --readme README.md
"""

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from html import escape
from pathlib import Path

from hero import hero
from theme import FONT, THEME

LANG_COLORS = ["#ff9f0a", "#8fb8de", "#a6dcef", "#ff8fa3", "#ffc27a", "#b8a99a"]
OTHER_COLOR = "#3a3a3c"
MARKUP = {"CSS", "SCSS", "HTML", "Dockerfile", "Makefile"}
MIN_REPO_BYTES = 1024
# A repo someone else owns (an organisation's, say) counts as a project of mine while I have at least
# MIN_OUTSIDE_COMMITS commits in it over the last ACTIVE_DAYS days.
MIN_OUTSIDE_COMMITS = 10
ACTIVE_DAYS = 90

QUERY = """
query($login: String!, $cursor: String, $since: DateTime!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    recent: contributionsCollection(from: $since) {
      commitContributionsByRepository(maxRepositories: 100) {
        contributions { totalCount }
        repository { ...repo }
      }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, privacy: PUBLIC,
                 isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { ...repo }
    }
  }
}

fragment repo on Repository {
  name url description isPrivate isFork isArchived pushedAt
  owner { login }
  primaryLanguage { name }
  languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
    edges { size node { name } }
  }
}
"""

W, H = 495, 210


def graphql(token, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-render"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch(login, token):
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=ACTIVE_DAYS)
    variables = {"login": login, "since": since.strftime("%Y-%m-%dT%H:%M:%SZ")}
    user = graphql(token, {**variables, "cursor": None})
    repos = list(user["repositories"]["nodes"])
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        more = graphql(token, {**variables, "cursor": page["endCursor"]})["repositories"]
        repos += more["nodes"]
        page = more["pageInfo"]
    # The query already filters on PUBLIC; double-check so a broader token can never leak a private repo.
    user["repos"] = [r for r in repos if not r["isPrivate"]]
    outside = [
        c["repository"]
        for c in user["recent"]["commitContributionsByRepository"]
        if c["contributions"]["totalCount"] >= MIN_OUTSIDE_COMMITS
        and c["repository"]["owner"]["login"].lower() != login.lower()
        and not c["repository"]["isPrivate"]
        and not c["repository"]["isFork"]
    ]
    # What the languages, the recent list and the hero show, newest push first. The profile repo's own
    # scripts aren't project work.
    user["projects"] = sorted(
        (r for r in user["repos"] + outside if not r["isArchived"] and r["name"] != login),
        key=lambda r: r["pushedAt"],
        reverse=True,
    )
    return user


def streaks(days):
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    i = len(counts) - 1
    if i >= 0 and counts[i] == 0:  # today isn't over yet
        i -= 1
    current = 0
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    return current, longest


def reveal(attr, start, end, delay, dur=0.4, spline=None):
    """Animate attr from start to end after delay. The element keeps its static value when SMIL doesn't run."""
    total = delay + dur
    ease = f' calcMode="spline" keySplines="0 0 1 1; {spline}"' if spline else ""
    return (
        f'<animate attributeName="{attr}" values="{start};{start};{end}" keyTimes="0;{delay / total:.3f};1"'
        f' dur="{total:.3f}s" fill="freeze"{ease}/>'
    )


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 10_000 else f"{n:,}"


def panel(title, note, body):
    """btop-style box: title cut into the top-left of the border, a dim note into the top-right."""
    tw, nw = len(title) * 7.2 + 16, len(note) * 6.6 + 16
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}">
  <style>
    text {{ font-family: {FONT}; }}
    .num {{ fill: {THEME['fg']}; font-size: 26px; font-weight: 700; }}
    .lbl {{ fill: {THEME['muted']}; font-size: 12px; }}
    .dim {{ fill: {THEME['dim']}; font-size: 11px; }}
  </style>
  <rect x="1" y="9" width="{W - 2}" height="{H - 10}" rx="10" fill="{THEME['bg']}" stroke="{THEME['border']}" stroke-width="1.5"/>
  <rect x="20" y="7" width="{tw:.0f}" height="4" fill="{THEME['bg']}"/>
  <text x="28" y="13" fill="{THEME['accent']}" font-size="12" font-weight="700">{escape(title)}</text>
  <rect x="{W - 20 - nw:.0f}" y="7" width="{nw:.0f}" height="4" fill="{THEME['bg']}"/>
  <text x="{W - 28}" y="13" text-anchor="end" class="dim">{escape(note)}</text>
{body}
</svg>
"""


def render_stats(user, today):
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    cells = [
        (fmt(cal["totalContributions"]), "contributions"),
        (f"{current}d", "current streak"),
        (f"{longest}d", "longest streak"),
        (fmt(len(user["repos"])), "public repos"),
        (fmt(user["pullRequests"]["totalCount"]), "pull requests"),
        (fmt(sum(1 for d in days if d["contributionCount"])), "active days"),
    ]
    out = []
    for i, (num, lbl) in enumerate(cells):
        x, y = 28 + (i % 3) * 156, 58 + (i // 3) * 56
        out.append(
            f'  <g>{reveal("opacity", 0, 1, i * 0.08)}'
            f'<text x="{x}" y="{y}" class="num">{escape(num)}</text>'
            f'<text x="{x}" y="{y + 18}" class="lbl">{escape(lbl)}</text></g>'
        )

    # Weekly contribution sparkline along the bottom.
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    peak = max(weeks) or 1
    x0, x1, base, hmax = 28, W - 28, 192, 38
    step = (x1 - x0) / len(weeks)
    for i, n in enumerate(weeks):
        h = max(2, round(n / peak * hmax))
        color = THEME["accent"] if n else THEME["border"]
        x = x0 + i * step
        out.append(
            f'  <rect x="{x:.1f}" y="{base - h}" width="{step - 2:.1f}" height="{h}" rx="1" fill="{color}" opacity="{0.35 + 0.65 * n / peak:.2f}">'
            f'{reveal("height", 0, h, 0.3 + i * 0.012)}{reveal("y", base, base - h, 0.3 + i * 0.012)}</rect>'
        )
    return panel("stats", f"last 12 months · {today:%d %b %Y}", "\n".join(out))


def render_languages(user):
    # Every project counts the same, so one repo with vendored JS can't drown out the rest.
    totals = {}
    for r in user["projects"]:
        sizes = {e["node"]["name"]: e["size"] for e in r["languages"]["edges"] if e["node"]["name"] not in MARKUP}
        repo_total = sum(sizes.values())
        if repo_total < MIN_REPO_BYTES:
            continue
        for name, size in sizes.items():
            totals[name] = totals.get(name, 0) + size / repo_total
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(totals.values()) or 1
    # Six legend slots: either six languages, or five plus "other".
    top = ranked if len(ranked) <= len(LANG_COLORS) else ranked[: len(LANG_COLORS) - 1]
    rest = total - sum(v for _, v in top)
    items = [(name, size, LANG_COLORS[i]) for i, (name, size) in enumerate(top)]
    if rest / total > 0.001:
        items.append(("other", rest, OTHER_COLOR))

    x0, bar_w, y = 28, W - 56, 50
    out = [
        f'  <clipPath id="bar"><rect x="{x0}" y="{y}" width="{bar_w}" height="10" rx="5">'
        f'{reveal("width", 0, bar_w, 0.1, 0.9, ".2 .8 .2 1")}</rect></clipPath>',
        f'  <rect x="{x0}" y="{y}" width="{bar_w}" height="10" rx="5" fill="{THEME["panel"]}"/>',
        '  <g clip-path="url(#bar)">',
    ]
    x = x0
    for name, size, color in items:
        w = size / total * bar_w
        out.append(f'    <rect x="{x:.1f}" y="{y}" width="{w + 0.5:.1f}" height="10" fill="{color}"/>')
        x += w
    out.append("  </g>")

    for i, (name, size, color) in enumerate(items):
        col, row = i % 2, i // 2
        lx, ly = x0 + col * 226, 106 + row * 34
        pct = size / total * 100
        out.append(
            f'  <g>{reveal("opacity", 0, 1, 0.4 + i * 0.07)}'
            f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>'
            f'<text x="{lx + 18}" y="{ly}" fill="{THEME["fg"]}" font-size="14">{escape(name)}</text>'
            f'<text x="{lx + 200}" y="{ly}" text-anchor="end" class="lbl">{pct:.1f}%</text></g>'
        )
    return panel("languages", "averaged per repo", "\n".join(out))


def render_recent(user, limit=5):
    lines = []
    for r in user["projects"]:
        if not r["description"]:
            continue
        lang = (r["primaryLanguage"] or {}).get("name")
        desc = r["description"].strip().rstrip(".").replace("<", "&lt;").replace(">", "&gt;")
        meta = f" · `{lang}`" if lang else ""
        lines.append(f"- **[{r['name']}]({r['url']})** · {desc}{meta}")
        if len(lines) == limit:
            break
    return "\n".join(lines)


def update_readme(path, block):
    text = path.read_text()
    new = re.sub(
        r"(<!-- RECENT:START -->).*?(<!-- RECENT:END -->)",
        lambda m: f"{m.group(1)}\n{block}\n{m.group(2)}",
        text,
        flags=re.S,
    )
    if new != text:
        path.write_text(new)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--login", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "rafiistcool"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--readme", type=Path)
    args = p.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or sys.exit("GITHUB_TOKEN is not set")
    user = fetch(args.login, token)
    today = dt.datetime.now(dt.timezone.utc).date()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "stats.svg").write_text(render_stats(user, today))
    (args.out / "languages.svg").write_text(render_languages(user))
    (args.out / "hero.svg").write_text(hero([r["name"] for r in user["projects"]]))
    if args.readme:
        update_readme(args.readme, render_recent(user))


if __name__ == "__main__":
    main()
