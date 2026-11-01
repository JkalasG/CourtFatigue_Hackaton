"""
README figures, drawn as plain SVG from the same JSON files the web app reads (web/data/).
Every number in an image is the number in the app: nothing is typed by hand.

Output : docs/img/fig_*.svg
Usage  : python scripts/build_readme_figures.py
"""

import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "web", "data")
OUT = os.path.join(ROOT, "docs", "img")

# Tactics-board palette of the web app; the two series colors pass the dataviz validator on BG (dark mode)
BG, INK, MUTED, GRID = "#1d1915", "#efe6d8", "#a89c8a", "#3a332c"
BLUE, ORANGE = "#4a8fd0", "#d9772e"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
W = 820


def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=13, fill=INK, anchor="start", weight=400):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{esc(s)}</text>')


def svg(h, title, subtitle, body, source):
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" '
            f'font-family="{FONT}" role="img" aria-label="{esc(title)}">'
            f'<rect width="{W}" height="{h}" rx="10" fill="{BG}"/>'
            + text(28, 40, title, 20, INK, weight=700) + text(28, 64, subtitle, 13, MUTED))
    return head + "".join(body) + text(28, h - 18, source, 11, MUTED) + "</svg>"


def save(name, content):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", os.path.join("docs", "img", name))


def fmt(v, d=2):
    return f"{v:+.{d}f}".replace("-", "−")


def curve(S):
    """Accuracy vs. the player's own level by time on court: cold start, then flat."""
    cold = {r["label"]: r for r in S["cold_start"] if r["group"] == "Time since entering"}
    rows = [(lab, cold[lab]) for lab in ("0–30 s", "30–60 s", "1–2 min")]
    rows += [(f'{b["lo_edge"]}–{b["hi_edge"]} min', b) for b in S["buckets"] if 2 <= b["lo_edge"] < 12]
    x0, x1, y0, y1, lo, hi = 90, W - 40, 100, 360, -2.5, 1.0
    X = lambda i: x0 + (i + 0.5) * (x1 - x0) / len(rows)
    Y = lambda v: y0 + (hi - v) / (hi - lo) * (y1 - y0)
    b = []
    for v in (-2, -1, 0, 1):
        b.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{INK if v == 0 else GRID}" '
                 f'stroke-width="{1.5 if v == 0 else 1}"{"" if v == 0 else " stroke-dasharray=\"2 4\""}/>')
        b.append(text(x0 - 10, Y(v) + 4, f"{fmt(v, 0)} pp" if v else "0", 12, MUTED, "end"))
    b.append(text(x0 + 6, Y(0) - 8, "player's normal level", 12, MUTED))
    split = (X(2) + X(3)) / 2
    b.append(f'<line x1="{split:.1f}" x2="{split:.1f}" y1="{y0}" y2="{y1}" stroke="{GRID}"/>')
    b.append(text((x0 + split) / 2, y0 - 8, "COLD START", 11, ORANGE, "middle", 700))
    b.append(text((split + x1) / 2, y0 - 8, "NO FATIGUE UP TO 12 MIN", 11, BLUE, "middle", 700))
    pts = []
    for i, (lab, r) in enumerate(rows):
        c = ORANGE if i < 3 else BLUE
        b.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{Y(r["lo_pp"]):.1f}" y2="{Y(r["hi_pp"]):.1f}" '
                 f'stroke="{c}" stroke-width="2" stroke-linecap="round"/>')
        pts.append((X(i), Y(r["effect_pp"]), c))
        b.append(text(X(i), y1 + 22, lab, 12, MUTED, "middle"))
    b.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)}" fill="none" '
             f'stroke="{MUTED}" stroke-width="1.5" stroke-opacity="0.6"/>')
    for x, y, c in pts:
        b.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{c}" stroke="{BG}" stroke-width="2"/>')
    first = rows[0][1]
    b.append(text(X(0) + 12, Y(first["effect_pp"]) + 4, f'{fmt(first["effect_pp"])} pp', 13, INK, weight=700))
    b.append(text((x0 + x1) / 2, y1 + 44, "Time on court since checking in (same stint)", 12, MUTED, "middle"))
    save("fig_curve.svg", svg(
        440, "Shooters don't tire. They start cold.",
        "Make rate vs. each player's own level, after discounting shot difficulty (xShot). Dots = estimate, bars = 95% CI.",
        b, f'NBA 2021-22 to 2024-25 · {S["n_shots"]:,} shots · source: web/data/summary.json'))


def replication(H):
    """Frozen 2021-25 estimates vs. the preregistered 2025-26 test."""
    lab = {"0–30 s": "Cold start, 0–30 s (primary test)", "30–60 s": "Cold start, 30–60 s",
           "1–2 min": "Cold start, 1–2 min"}
    rows = [(lab[k], v) for k, v in H["cold_start"].items()]
    rows.append(("Fatigue: ≥ 8 min vs. 2–6 min", H["fatigue_8plus_vs_2_6"]))
    x0, x1, y0, lo, hi, step = 300, W - 110, 110, -2.5, 1.5, 62
    X = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    y1 = y0 + step * len(rows)
    b = []
    for v in (-2, -1, 0, 1):
        b.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="{y0 - 10}" y2="{y1}" stroke="{INK if v == 0 else GRID}" '
                 f'stroke-width="{1.5 if v == 0 else 1}"{"" if v == 0 else " stroke-dasharray=\"2 4\""}/>')
        b.append(text(X(v), y1 + 18, f"{fmt(v, 0)} pp" if v else "0", 12, MUTED, "middle"))
    b.append(f'<circle cx="{x0}" cy="88" r="5" fill="{BLUE}"/>' + text(x0 + 10, 92, "2021-25 (frozen before the test)", 12, INK))
    b.append(f'<circle cx="{x0 + 240}" cy="88" r="5" fill="{ORANGE}"/>' + text(x0 + 250, 92, "2025-26 (never seen)", 12, INK))
    for i, (name, r) in enumerate(rows):
        yc = y0 + i * step + 20
        b.append(text(28, yc + 4, name, 13, INK, weight=700 if i == 0 else 400))
        for dy, c, est, ci in ((-9, BLUE, r["frozen"], r["frozen_ci95"]), (9, ORANGE, r["new"], r["ci95"])):
            b.append(f'<line x1="{X(ci[0]):.1f}" x2="{X(ci[1]):.1f}" y1="{yc + dy}" y2="{yc + dy}" stroke="{c}" '
                     f'stroke-width="2" stroke-linecap="round"/>')
            b.append(f'<circle cx="{X(est):.1f}" cy="{yc + dy}" r="5" fill="{c}" stroke="{BG}" stroke-width="2"/>')
        b.append(text(W - 28, yc + 13, f'{fmt(r["new"])} pp', 12, INK, "end", 700))
    save("fig_replication.svg", svg(
        y1 + 56, "It held up on a season the model never saw",
        "Plan, frozen estimates and success rule committed before downloading 2025-26. Verdict on the primary test: replicated.",
        b, f'2025-26: {H["games"]:,} games · {H["shots"]:,} shots · source: web/data/holdout_replication.json'))


def placebo(S):
    """Naive 'bench them after a 3-point drop' rule vs. inference, on real and shuffled minutes."""
    p = S["placebo"]
    groups = [("Naive rule: “sub them if they drop 3 pts”", p["naive_real"], p["naive_placebo"]),
              ("CourtFatigue: 95% CI + Benjamini-Hochberg", p["inference_real"], p["inference_placebo"])]
    x0, x1 = 330, W - 80
    X = lambda v: x0 + v * (x1 - x0)
    b = [f'<rect x="{x0}" y="82" width="10" height="10" rx="2" fill="{BLUE}"/>' + text(x0 + 16, 92, "real minutes", 12, INK),
         f'<rect x="{x0 + 130}" y="82" width="10" height="10" rx="2" fill="{ORANGE}"/>'
         + text(x0 + 146, 92, "minutes shuffled within player (fatigue impossible)", 12, INK)]
    for i, (name, real, fake) in enumerate(groups):
        yc = 130 + i * 80
        b.append(text(28, yc + 16, name, 13, INK))
        for dy, c, v in ((0, BLUE, real), (20, ORANGE, fake)):
            w = max(X(v) - x0, 2)
            b.append(f'<rect x="{x0}" y="{yc + dy}" width="{w:.1f}" height="16" rx="3" fill="{c}"/>')
            b.append(text(x0 + w + 8, yc + dy + 13, f"{v * 100:.{2 if v < 0.01 and v > 0 else 1}f}% flagged", 12, INK))
    save("fig_placebo.svg", svg(
        320, "A popular coaching rule is noise",
        f'Share of players flagged as “gets tired” ({p["n_players"]} players). If a rule flags as many with random minutes, it is not seeing fatigue.',
        b, f'Placebo with {p["n_perm"]} permutations · source: web/data/summary.json'))


def cost(X_):
    """Points per team-season: cold start vs. back-to-backs."""
    c, b2b = X_["impact"]["cold"], X_["impact"]["b2b"]
    rows = [("Cold start (first 2 min after checking in)", c["total"]["pts"], c["total"]["lo"], c["total"]["hi"]),
            ("Back-to-backs (2nd game in 2 days)", b2b["pts"], b2b["lo"], b2b["hi"])]
    x0, x1, lo = 340, W - 60, -40
    X = lambda v: x0 + v / lo * (x1 - x0)
    b = []
    for v in (0, -10, -20, -30, -40):
        b.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="92" y2="232" stroke="{INK if v == 0 else GRID}"'
                 f'{"" if v == 0 else " stroke-dasharray=\"2 4\""}/>')
        b.append(text(X(v), 250, f"{v:.0f}".replace("-", "−"), 12, MUTED, "middle"))
    for i, (name, pts, lo_, hi_) in enumerate(rows):
        yc = 112 + i * 60
        b.append(text(28, yc + 14, name, 13, INK))
        b.append(f'<rect x="{x0}" y="{yc}" width="{X(pts) - x0:.1f}" height="20" rx="3" fill="{ORANGE if i == 0 else BLUE}"/>')
        b.append(f'<line x1="{X(hi_):.1f}" x2="{X(lo_):.1f}" y1="{yc + 10}" y2="{yc + 10}" stroke="{INK}" stroke-width="1.5"/>')
        b.append(text(X(lo_) + 8, yc + 15, f"{pts:.0f} pts".replace("-", "−"), 13, INK, weight=700))
    save("fig_cost.svg", svg(
        300, "The cold start costs more than twice what back-to-backs do",
        f'Points per team per season (95% CI). Cold start ≈ {abs(c["wins"]["pts"]):.1f} wins at ~{X_["impact"]["points_per_win"]:.0f} points per win.',
        b, "Full cost vs. the player's own level, not what a coach can recover · source: web/data/extra.json"))


if __name__ == "__main__":
    S, H, E = load("summary.json"), load("holdout_replication.json"), load("extra.json")
    curve(S)
    replication(H)
    placebo(S)
    cost(E)
