#!/usr/bin/env python3
"""Write assets/hero.svg: a small animated Hyprland desktop in the Omarchy theme.

    python3 scripts/hero.py

Everything animates with SMIL so it plays inside GitHub's <img>. Static attribute values are the final
frame, so viewers without SMIL still see the full picture.
"""

from html import escape
from pathlib import Path

from render import FONT, THEME as T

W, H = 1200, 440
LOOP = 14.0  # seconds
RESET = LOOP - 0.6  # terminal clears here and starts over

# Layout: bar on top, terminal on the left, herdr and fastfetch stacked on the right.
BAR_H, GAP, PAD = 32, 10, 12
TOP = BAR_H + GAP
LEFT = (PAD, TOP, 620, H - PAD - TOP)
RIGHT_X = PAD + LEFT[2] + GAP
RIGHT_W = W - PAD - RIGHT_X
HERDR = (RIGHT_X, TOP, RIGHT_W, 180)
FETCH = (RIGHT_X, TOP + 180 + GAP, RIGHT_W, H - PAD - (TOP + 180 + GAP))

FS = 17  # terminal font size
CW = FS * 0.6  # monospace advance
CHAR_DELAY = 0.085

# (command, baseline y, outputs). Output kinds: name, text, dirs.
SCRIPT = [
    ("whoami", 88, [("name", 148, "Rafael Till")]),
    ("cat now.txt", 204, [("text", 234, ["omarchy plugins", "hyprland tweaks", "agent tooling"])]),
    ("ls ~/Projects", 290, [
        ("dirs", 320, "ferrite  omarchy-kb-layout  omarchy-protonvpn"),
        ("dirs", 348, "omarchy-wireguard  tillhome  ti4-host-leitfaden"),
    ]),
]
FINAL_PROMPT_Y = 398

# (agent, repo, [(start time, state)]); states cycle within the loop.
AGENTS = [
    ("claude", "omarchy-wireguard", [(0, "working")]),
    ("codex", "tillhome", [(0, "working"), (6.2, "done")]),
    ("claude", "ferrite", [(0, "idle"), (8.4, "working")]),
]

FETCH_ROWS = [
    ("os", "Omarchy (Arch Linux)"),
    ("wm", "Hyprland 0.56"),
    ("term", "ghostty"),
    ("shell", "bash + starship"),
    ("editor", "neovim"),
    ("agents", "herdr · claude code · codex"),
]
PALETTE = [T["red"], T["accent"], "#ffc27a", T["blue"], "#ff8fa3", T["cyan"], T["muted"], T["fg"]]


def discrete(attr, frames, dur=LOOP):
    """Looping step animation from [(time, value)]; the first frame must be at t=0."""
    values = ";".join(str(v) for _, v in frames)
    times = ";".join(f"{t / dur:.4f}" for t, _ in frames)
    return (
        f'<animate attributeName="{attr}" values="{values}" keyTimes="{times}" dur="{dur}s"'
        ' calcMode="discrete" repeatCount="indefinite"/>'
    )


def visible(start, end=RESET):
    return discrete("opacity", [(0, 0), (start, 1), (end, 0)] if start else [(0, 1), (end, 0)])


def text(x, y, s, fill=T["fg"], size=FS, extra=""):
    return f'<text x="{x:.1f}" y="{y}" fill="{fill}" font-size="{size}"{extra}>{escape(s)}</text>'


def tile(x, y, w, h, focused=False):
    stroke = T["accent"] if focused else "#3a3a3c"
    return f'<rect x="{x + 1}" y="{y + 1}" width="{w - 2}" height="{h - 2}" rx="3" fill="{T["bg"]}" stroke="{stroke}" stroke-width="2"/>'


def spinner(cx, cy, color):
    return (
        f'<g transform="translate({cx:.1f} {cy})">'
        f'<circle r="6" fill="none" stroke="{color}" stroke-opacity=".25" stroke-width="2"/>'
        f'<path d="M0 -6A6 6 0 0 1 6 0" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round">'
        '<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur=".9s" repeatCount="indefinite"/>'
        "</path></g>"
    )


def bar():
    y = 21
    out = [f'<rect width="{W}" height="{BAR_H}" fill="{T["panel"]}"/>']
    # Launcher glyph and workspaces.
    out.append(f'<rect x="16" y="9" width="14" height="14" rx="2" fill="none" stroke="{T["fg"]}" stroke-width="1.5"/>')
    out.append(f'<path d="M20 9V23" stroke="{T["fg"]}" stroke-width="1.5"/>')
    for i in range(5):
        color = T["fg"] if i == 0 else T["muted"] if i < 3 else T["dim"]
        weight = ' font-weight="700"' if i == 0 else ""
        out.append(text(46 + i * 22, y, str(i + 1), color, 15, weight))
    out.append(text(W / 2, y, "20:25", T["fg"], 15, ' text-anchor="middle"'))
    # Right side: agents indicator, keyboard layout, VPN shield, wifi.
    out.append(
        f'<circle cx="1052" cy="16" r="4" fill="{T["accent"]}">'
        '<animate attributeName="opacity" values="1;.3;1" dur="1.6s" repeatCount="indefinite"/></circle>'
    )
    out.append(text(1062, y, "2", T["fg"], 15))
    out.append(text(1092, y, "us", T["muted"], 15))
    out.append(f'<path d="M1136 8l7 3v5c0 4-3 7-7 8-4-1-7-4-7-8v-5z" fill="{T["accent"]}" fill-opacity=".9"/>')
    out.append(
        f'<g fill="none" stroke="{T["fg"]}" stroke-width="1.6" stroke-linecap="round">'
        '<path d="M1160 13a12 12 0 0 1 16 0"/><path d="M1163 17a7 7 0 0 1 10 0"/></g>'
        f'<circle cx="1168" cy="21" r="1.8" fill="{T["fg"]}"/>'
    )
    return "\n".join(out)


def terminal():
    x0 = LEFT[0] + 24
    px = x0 + 4 * CW  # after "~ ❯ "
    out, cursor = [tile(*LEFT, focused=True)], []
    shown_at = 0.0  # when the current prompt appears

    def prompt(y, start):
        anim = visible(start) if start else ""
        arrow = text(x0 + 2 * CW, y, "❯", T["accent"], extra=' font-weight="700"')
        return f"<g>{anim}{text(x0, y, '~', T['blue'])}{arrow}</g>"

    for n, (cmd, y, outputs) in enumerate(SCRIPT):
        out.append(prompt(y, shown_at))
        cursor.append((shown_at, px, y))
        start = shown_at + (0.7 if n == 0 else 0.55)
        widths = [(0, 0)]
        for k in range(1, len(cmd) + 1):
            t = start + k * CHAR_DELAY
            widths.append((t, round(k * CW, 1)))
            cursor.append((t, round(px + k * CW, 1), y))
        widths.append((RESET, 0))
        out.append(
            f'<clipPath id="type{n}"><rect x="{px:.1f}" y="{y - FS}" width="{(len(cmd) + 1) * CW:.1f}" height="{FS * 1.5}">'
            f'{discrete("width", widths)}</rect></clipPath>'
        )
        out.append(f'<g clip-path="url(#type{n})">{text(px, y, cmd)}</g>')

        done = start + len(cmd) * CHAR_DELAY + 0.35
        for kind, oy, content in outputs:
            if kind == "name":
                body = text(x0, oy, content, T["fg"], 54, ' font-weight="700" letter-spacing="-1"')
            elif kind == "dirs":
                # Non-breaking spaces: SVG renderers collapse runs of normal ones.
                body = text(x0, oy, content.replace(" ", "\u00a0"), T["blue"], extra=' font-weight="700"')
            else:
                sep = f'<tspan fill="{T["accent"]}"> · </tspan>'
                body = f'<text x="{x0}" y="{oy}" fill="{T["fg"]}" font-size="{FS}">{sep.join(escape(p) for p in content)}</text>'
            out.append(f"<g>{visible(done)}{body}</g>")
        shown_at = round(done + 0.1, 3)

    out.append(prompt(FINAL_PROMPT_Y, shown_at))
    cursor.append((shown_at, px, FINAL_PROMPT_Y))
    cursor.append((RESET, px, SCRIPT[0][1]))

    xs = [(t, x) for t, x, _ in cursor]
    ys = [(t, y - FS + 3) for t, _, y in cursor]
    out.append(
        '<g><animate attributeName="opacity" values="1;0" keyTimes="0;.5" dur="1.05s" calcMode="discrete" repeatCount="indefinite"/>'
        f'<rect x="{px:.1f}" y="{FINAL_PROMPT_Y - FS + 3}" width="{CW:.1f}" height="{FS + 2}" fill="{T["fg"]}" fill-opacity=".85">'
        f"{discrete('x', xs)}{discrete('y', ys)}</rect></g>"
    )
    return "\n".join(out)


def herdr():
    x, y, w, h = HERDR
    left, right = x + 22, x + w - 22
    out = [
        tile(*HERDR),
        text(left, y + 30, "herdr", T["accent"], 15, ' font-weight="700"'),
        text(right, y + 30, "agents", T["dim"], 14, ' text-anchor="end"'),
        f'<path d="M{left} {y + 44}H{right}" stroke="{T["border"]}" stroke-width="1.5"/>',
    ]
    for i, (agent, repo, states) in enumerate(AGENTS):
        ry = y + 78 + i * 34
        out.append(text(left + 18, ry, agent, T["fg"], 16, ' font-weight="700"'))
        out.append(text(left + 102, ry, repo, T["muted"], 16))
        for j, (start, state) in enumerate(states):
            if state == "working":
                color = T["accent"]
                dot = (
                    f'<circle cx="{left + 5}" cy="{ry - 5}" r="5" fill="{color}">'
                    '<animate attributeName="opacity" values="1;.35;1" dur="1.6s" repeatCount="indefinite"/></circle>'
                )
                mark = spinner(right - 82, ry - 5, color)
            elif state == "done":
                color = T["cyan"]
                dot = f'<circle cx="{left + 5}" cy="{ry - 5}" r="5" fill="{color}"/>'
                mark = f'<path d="M{right - 64} {ry - 5}l4 4 7-8" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            else:
                color = T["dim"]
                dot = f'<circle cx="{left + 5}" cy="{ry - 5}" r="4.2" fill="none" stroke="{color}" stroke-width="1.6"/>'
                mark = ""
            label = text(right, ry, state, color, 16, ' text-anchor="end"')
            if len(states) == 1:
                anim = ""
            else:
                end = states[j + 1][0] if j + 1 < len(states) else None
                frames = [(0, 1 if start == 0 else 0)]
                if start:
                    frames.append((start, 1))
                if end:
                    frames.append((end, 0))
                anim = discrete("opacity", frames)
            # The static (no-SMIL) frame shows each agent's last state.
            static = "" if j == len(states) - 1 else ' opacity="0"'
            out.append(f"<g{static}>{anim}{dot}{mark}{label}</g>")
    return "\n".join(out)


def fastfetch():
    x, y, w, h = FETCH
    left = x + 22
    out = [
        tile(*FETCH),
        f'<text x="{left}" y="{y + 32}" font-size="16" font-weight="700">'
        f'<tspan fill="{T["accent"]}">rafi</tspan><tspan fill="{T["muted"]}">@</tspan><tspan fill="{T["accent"]}">omarchy</tspan></text>',
        f'<path d="M{left} {y + 44}H{left + 12 * 9.6}" stroke="{T["dim"]}" stroke-width="1.5"/>',
    ]
    for i, (key, value) in enumerate(FETCH_ROWS):
        ry = y + 70 + i * 21
        out.append(text(left, ry, key, T["accent"], 15, ' font-weight="700"'))
        out.append(text(left + 8 * 9, ry, value, T["fg"], 15))
    sw, gap = 22, 5
    px0 = x + w - 22 - 4 * sw - 3 * gap
    for i, color in enumerate(PALETTE):
        out.append(
            f'<rect x="{px0 + (i % 4) * (sw + gap)}" y="{y + 20 + (i // 4) * (14 + gap)}" width="{sw}" height="14" rx="2" fill="{color}"/>'
        )
    return "\n".join(out)


def hero():
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
<title id="title">Rafael Till</title>
<desc id="desc">An animated Hyprland desktop: a terminal introducing Rafael Till, an agent monitor, and system info.</desc>
<defs>
  <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#1b2430"/>
    <stop offset=".55" stop-color="#4a3a34"/>
    <stop offset="1" stop-color="#c9772a"/>
  </linearGradient>
  <radialGradient id="sun" cx=".72" cy="1" r=".6">
    <stop offset="0" stop-color="{T["accent"]}" stop-opacity=".55"/>
    <stop offset="1" stop-color="{T["accent"]}" stop-opacity="0"/>
  </radialGradient>
  <clipPath id="screen"><rect width="{W}" height="{H}" rx="14"/></clipPath>
</defs>
<style>text {{ font-family: {FONT}; }}</style>
<g clip-path="url(#screen)">
<rect width="{W}" height="{H}" fill="url(#sky)"/>
<rect width="{W}" height="{H}" fill="url(#sun)"/>
{bar()}
{terminal()}
{herdr()}
{fastfetch()}
</g>
</svg>
"""


if __name__ == "__main__":
    path = Path(__file__).resolve().parent.parent / "assets" / "hero.svg"
    path.write_text(hero())
    print(f"wrote {path}")
