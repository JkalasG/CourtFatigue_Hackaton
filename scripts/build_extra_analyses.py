"""
Extra analyses for the coaching message (kept apart from the main pipeline, which is not touched).

  1. Impact: points (and approximate wins) per team and season lost to the cold start and to
     back-to-backs. Cold start: sum of (make deviation x shot value) over shots in the first 2 min,
     with a 95% CI from a game bootstrap. Back-to-back: the fixed-effects coefficient times the
     points attempted in back-to-back games.
  2. Cold start by shot type (three, mid-range, near the rim), Benjamini-Hochberg across types.
  3. Selection bias: how each stint ends (normal substitution, timeout, between quarters,
     foul trouble, halftime/end of game). The long-vs-warmed-up contrast is repeated for stints
     cut by something unrelated to tiredness (halftime/end of game, foul trouble).
  4. Free throws: no defender and fixed distance. Same contrast and cold start.

Inputs : data/processed/shots_fatigue_processed.csv and the raw play-by-play of each season.
Output : web/data/extra.json (plus data/processed/extra/*.csv as a cache of the play-by-play pass).

Usage: python scripts/build_extra_analyses.py [--rebuild]
"""

import json
import os
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import fatigue_stats as fs  # noqa: E402
from src.stint_calculator import (HALFTIME_PERIOD, _valid_player, parse_clock_to_seconds,  # noqa: E402
                                  period_length, period_start, season_paths)
from scripts.build_web_data import clean  # noqa: E402

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SRC = "data/processed/shots_fatigue_processed.csv"
CACHE = "data/processed/extra"
OUT = "web/data/extra.json"
SEASONS = ["2021", "2022", "2023", "2024"]
SHORT_LO, SHORT, LONG = fs.SHORT_LO_DEFAULT, fs.SHORT_DEFAULT, fs.LONG_DEFAULT
POINTS_PER_WIN = 30.0   # rule of thumb: ~30 points of season point differential per win
N_BOOT = 2000
COLD_BUCKETS = ((0, 0.5, "0–30 s"), (0.5, 1, "30–60 s"), (1, 2, "1–2 min"))
FOUL_COUNT = re.compile(r"\(P(\d+)\.")
EXOGENOUS = ("period_end", "foul_trouble")
END_WINDOW = 2.0        # minutes before the stint ends checked for "pulled after a cold streak"
FIRST_ENTRY, HALFTIME = -1.0, -2.0   # bench_sec codes: first stint of the game / stint starting the 3rd quarter
BENCH_BUCKETS = ((0, 3, "< 3 min"), (3, 6, "3–6 min"), (6, 10, "6–10 min"), (10, 15, "10–15 min"), (15, 99, "> 15 min"))


def foul_trouble(fouls: int, period: int) -> bool:
    """Usual coaching rule: 2 fouls in Q1, 3 in Q2, 4 in Q3, 5 in Q4/OT."""
    return fouls >= min(period, 4) + 1


def walk_game(pbp_game: pd.DataFrame):
    """
    Same walk as src/stint_calculator.reconstruct_game_stints (same stint rule), plus:
      * how the stint of every field-goal attempt ends -> (GAME_ID, EVENTNUM, PLAYER_ID, stint_sec, bench_sec,
                                                         sec_to_end, end_reason)
        bench_sec = game-clock seconds on the bench before this stint; FIRST_ENTRY / HALFTIME are codes
      * every free throw with the shooter's stint     -> (GAME_ID, EVENTNUM, PLAYER_ID, TEAM_ID, PERIOD,
                                                         stint_sec, made, home, inferred)
    """
    ends, fts = [], []
    on = {}        # team_id -> {player_id: [game_entry, stint_entry, inferred]}
    pending = {}   # player_id -> field-goal rows of the current stint still waiting for their end reason
    fouls = {}     # player_id -> personal fouls (official count in the description)
    last_foul = {}  # player_id -> game second of the last personal foul
    timeouts = set()  # game seconds with a timeout
    last_exit = {}  # player_id -> game second they last left the court
    bench = {}      # player_id -> bench seconds before the current stint
    gid = pbp_game.GAME_ID.iloc[0]

    def enter(pid, t, period):
        bench[pid] = HALFTIME if period == HALFTIME_PERIOD and t == period_start(period) else             (t - last_exit[pid] if pid in last_exit else FIRST_ENTRY)

    def close(pid, reason, t_end):
        for *r, t_shot in pending.pop(pid, []):
            ends.append((*r, t_end - t_shot, reason))

    periods = sorted(pbp_game.PERIOD.unique())
    for period, p in pbp_game.groupby("PERIOD", sort=True):
        p = p.sort_values("EVENTNUM", kind="stable")
        ps = period_start(period)
        plen = period_length(period)

        if period == HALFTIME_PERIOD:
            for pid in list(pending):
                close(pid, "period_end", ps)  # halftime cuts every stint
            for team in on.values():
                for pid, v in team.items():
                    v[1] = ps
                    bench[pid] = HALFTIME

        first = {}
        for r in p.itertuples(index=False):
            for k, (pid, ptype, tid) in enumerate((
                (r.PLAYER1_ID, r.PERSON1TYPE, r.PLAYER1_TEAM_ID),
                (r.PLAYER2_ID, r.PERSON2TYPE, r.PLAYER2_TEAM_ID),
                (r.PLAYER3_ID, r.PERSON3TYPE, r.PLAYER3_TEAM_ID),
            ), 1):
                if _valid_player(pid, ptype) and pid not in first:
                    first[pid] = (tid, r.EVENTMSGTYPE == 8 and k == 2)
        continuing = {pid for pid, (_, sub) in first.items() if not sub}
        for pid in list(pending):
            if pid not in continuing:
                close(pid, "between_quarters", ps)  # did not start this quarter: coach's decision at the break
        for team in on.values():
            for pid, v in team.items():
                # on court when the previous quarter ended but not now: left at the break (record it once)
                if period > 1 and pid not in continuing and last_exit.get(pid, -1) < v[0]:
                    last_exit[pid] = ps
        for pid, (tid, entered_as_sub) in first.items():
            team = on.setdefault(tid, {})
            if not entered_as_sub and pid not in team:
                team[pid] = [ps, ps, False]
                enter(pid, ps, period)

        for r in p.itertuples(index=False):
            t = ps + (plen - parse_clock_to_seconds(r.PCTIMESTRING))
            et = r.EVENTMSGTYPE

            if et == 9:
                timeouts.add(t)
            elif et == 6 and _valid_player(r.PLAYER1_ID, r.PERSON1TYPE):
                desc = r.HOMEDESCRIPTION if r.PERSON1TYPE == 4 else r.VISITORDESCRIPTION
                m = FOUL_COUNT.search(str(desc))
                if m:  # personal fouls carry "(P<n>." ; technicals do not
                    fouls[r.PLAYER1_ID] = int(m.group(1))
                    last_foul[r.PLAYER1_ID] = t

            if et == 8:
                pid = r.PLAYER1_ID
                team = on.setdefault(r.PLAYER1_TEAM_ID, {})
                if team.pop(pid, None) is not None:
                    last_exit[pid] = t
                if pid in pending:
                    if last_foul.get(pid) == t and foul_trouble(fouls.get(pid, 0), period):
                        close(pid, "foul_trouble", t)
                    elif t in timeouts:
                        close(pid, "timeout", t)
                    else:
                        close(pid, "substitution", t)
                if r.PLAYER2_ID == r.PLAYER2_ID and r.PLAYER2_ID > 0:
                    team[r.PLAYER2_ID] = [t, t, False]
                    enter(r.PLAYER2_ID, t, period)

            elif et in (1, 2, 3):
                pid = r.PLAYER1_ID
                if not _valid_player(pid, r.PERSON1TYPE):
                    continue
                team = on.setdefault(r.PLAYER1_TEAM_ID, {})
                v = team.get(pid)
                if v is None:
                    v = [ps, ps, True]
                    team[pid] = v
                stint = max(0, t - v[1])
                if et == 3:
                    desc = r.HOMEDESCRIPTION if r.PERSON1TYPE == 4 else r.VISITORDESCRIPTION
                    if "Free Throw" not in str(desc):
                        continue
                    fts.append((gid, r.EVENTNUM, int(pid), int(r.PLAYER1_TEAM_ID), period, stint,
                                not str(desc).startswith("MISS"), r.PERSON1TYPE == 4, bool(v[2])))
                else:
                    b = np.nan if v[2] else bench.get(pid, np.nan)
                    pending.setdefault(pid, []).append((gid, r.EVENTNUM, int(pid), stint, b, t))

        if period == periods[-1]:
            for pid in list(pending):
                close(pid, "period_end", ps + plen)  # end of the game
    return ends, fts


def play_by_play_pass(rebuild: bool):
    ends_path, fts_path = os.path.join(CACHE, "stint_ends.csv"), os.path.join(CACHE, "free_throws.csv")
    if not rebuild and os.path.exists(ends_path) and os.path.exists(fts_path):
        ends = pd.read_csv(ends_path)
        if "bench_sec" in ends.columns:
            return ends, pd.read_csv(fts_path, dtype={"SEASON": str})
    all_ends, all_fts = [], []
    for season in SEASONS:
        pbp_path, _ = season_paths(season)
        print(f"[{season}] play-by-play pass: {pbp_path}")
        pbp = pd.read_csv(pbp_path, low_memory=False)
        for i, (_, g) in enumerate(pbp.groupby("GAME_ID"), 1):
            e, f = walk_game(g)
            all_ends.extend(e)
            all_fts.extend((*row, season) for row in f)
            if i % 400 == 0:
                print(f"   [{season}] {i} games")
    ends = pd.DataFrame(all_ends, columns=["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "stint_sec_check", "bench_sec",
                                       "sec_to_end", "end_reason"])
    fts = pd.DataFrame(all_fts, columns=["GAME_ID", "EVENTNUM", "PLAYER_ID", "TEAM_ID", "PERIOD", "stint_seconds",
                                         "made", "is_home", "stint_inferred", "SEASON"])
    os.makedirs(CACHE, exist_ok=True)
    ends.to_csv(ends_path, index=False)
    fts.to_csv(fts_path, index=False)
    return ends, fts


def contrast_fe(d: pd.DataFrame, stint_col: str = "stint_minutes") -> dict:
    """Long (>= LONG) vs warmed up (SHORT_LO-SHORT) with player-season fixed effects, clustered CI."""
    sub = d[((d[stint_col] >= SHORT_LO) & (d[stint_col] < SHORT)) | (d[stint_col] >= LONG)].copy()
    sub["long"] = (sub[stint_col] >= LONG).astype(float)
    r = fs.fe_slope(sub, ["long"]).iloc[0]
    return {"effect_pp": r.coef_pp, "lo_pp": r.lo_pp, "hi_pp": r.hi_pp, "se_pp": r.se_pp,
            "n": int(r.n), "n_long": int(sub["long"].sum())}


def slope_warm(d: pd.DataFrame) -> dict:
    r = fs.fe_slope(d[d.stint_minutes >= SHORT_LO], ["stint_minutes"]).iloc[0]
    return {"coef_pp": r.coef_pp, "lo_pp": r.lo_pp, "hi_pp": r.hi_pp, "n": int(r.n)}


def cold_rows(d: pd.DataFrame) -> list:
    """Cold-start buckets plus the 2-4 min reference (deviation from the player-season mean)."""
    d = fs.add_dev(d)
    out = []
    for lo, hi, lab in COLD_BUCKETS + ((2, 4, "2–4 min (reference)"),):
        out.append({"label": lab, **fs._cluster_mean(d[(d.stint_minutes >= lo) & (d.stint_minutes < hi)])})
    return out


def p_value(effect, se):
    return 2 * (1 - float(fs._norm_cdf(abs(effect / se)))) if se else 1.0


def impact(df: pd.DataFrame, rng) -> dict:
    """Points and wins per team-season lost to the cold start and to back-to-backs."""
    d = fs.add_dev(df)
    d["value"] = np.where(d.SHOT_TYPE == "3PT Field Goal", 3.0, 2.0)
    n_ts = d.groupby(["TEAM_ID", "SEASON"]).ngroups
    n_games_team = d.groupby(["TEAM_ID", "SEASON"]).GAME_ID.nunique().mean()

    # Cold start: points below each shooter's normal, shot by shot, game bootstrap for the CI
    cold = d[d.stint_minutes < 2].copy()
    cold["bucket"] = pd.cut(cold.stint_minutes, [b[0] for b in COLD_BUCKETS] + [2], right=False,
                            labels=[b[2] for b in COLD_BUCKETS])
    cold["pts"] = cold.dev * cold.value
    per_game = cold.pivot_table(index="GAME_ID", columns="bucket", values="pts", aggfunc="sum",
                                observed=False).reindex(d.GAME_ID.unique()).fillna(0.0)
    tot = per_game.values  # games x buckets
    idx = rng.integers(0, len(tot), size=(N_BOOT, len(tot)))
    boot = np.stack([tot[i].sum(axis=0) for i in idx]) / n_ts  # N_BOOT x buckets
    point = tot.sum(axis=0) / n_ts
    buckets = []
    for j, lab in enumerate(per_game.columns):
        sub = cold[cold.bucket == lab]
        buckets.append({"label": str(lab), "shots_per_team_season": len(sub) / n_ts,
                        "pts": point[j], "lo": np.percentile(boot[:, j], 2.5), "hi": np.percentile(boot[:, j], 97.5)})
    total_boot = boot.sum(axis=1)
    total = {"pts": point.sum(), "lo": np.percentile(total_boot, 2.5), "hi": np.percentile(total_boot, 97.5)}
    # Check with the plan's formula: shots x measured drop x shot value
    measured = {r["label"]: r["effect_pp"] for r in cold_rows(df)}
    formula = sum((cold[cold.bucket == lab].value.sum() / n_ts) * measured[lab] / 100 for lab in per_game.columns)

    # Back-to-back: fixed-effects coefficient (with the same controls as the main analysis) x points attempted
    full = ["stint_minutes", "game_minutes_played", "is_home", "score_margin", "b2b"]
    b = fs.fe_slope(df, full).set_index("term").loc["b2b"]
    b2b = d[d.b2b == 1]
    val_ts = b2b.value.sum() / n_ts
    b2b_games = b2b.groupby(["TEAM_ID", "SEASON"]).GAME_ID.nunique().mean()

    def wins(x):
        return x / POINTS_PER_WIN

    return {
        "n_team_seasons": int(n_ts), "games_per_team_season": float(n_games_team), "points_per_win": POINTS_PER_WIN,
        "cold": {"buckets": buckets, "total": total, "formula_pts": float(formula),
                 "per_game": {k: v / n_games_team for k, v in total.items()},
                 "wins": {k: wins(v) for k, v in total.items()},
                 "shots_per_team_season": float(len(cold) / n_ts),
                 "share_of_fga": float(len(cold) / len(d))},
        "b2b": {"coef_pp": b.coef_pp, "lo_pp": b.lo_pp, "hi_pp": b.hi_pp,
                "games_per_team_season": float(b2b_games),
                "pts": val_ts * b.coef_pp / 100, "lo": val_ts * b.lo_pp / 100, "hi": val_ts * b.hi_pp / 100,
                "per_b2b_game": val_ts * b.coef_pp / 100 / b2b_games,
                "wins": {"pts": wins(val_ts * b.coef_pp / 100), "lo": wins(val_ts * b.lo_pp / 100),
                         "hi": wins(val_ts * b.hi_pp / 100)}},
    }


def by_shot_type(df: pd.DataFrame) -> list:
    """Cold start by shot type (0-30 s, 30-60 s, 1-2 min and the whole 0-2 min); BH across all the tests."""
    groups = {"Three-pointer": df.SHOT_TYPE == "3PT Field Goal",
              "Mid-range": df.SHOT_ZONE_BASIC == "Mid-Range",
              "Near the rim (paint)": df.SHOT_ZONE_BASIC.isin(["Restricted Area", "In The Paint (Non-RA)"])}
    d = fs.add_dev(df)  # deviation from the player's overall level, as in the main cold-start table
    rows = []
    for name, mask in groups.items():
        sub = d[mask.values]
        for lo, hi, lab in ((0, 0.5, "0–30 s"), (0.5, 1, "30–60 s"), (1, 2, "1–2 min"), (0, 2, "0–2 min")):
            r = fs._cluster_mean(sub[(sub.stint_minutes >= lo) & (sub.stint_minutes < hi)])
            # compare against the same shot type once warmed up (2-4 min), so shot-type mix does not leak in
            ref = fs._cluster_mean(sub[(sub.stint_minutes >= 2) & (sub.stint_minutes < 4)])
            se = (r["hi_pp"] - r["lo_pp"]) / (2 * fs.Z95)
            se_ref = (ref["hi_pp"] - ref["lo_pp"]) / (2 * fs.Z95)
            diff, se_d = r["effect_pp"] - ref["effect_pp"], float(np.hypot(se, se_ref))
            rows.append({"type": name, "window": lab, "n": r["n"], "effect_pp": r["effect_pp"],
                         "lo_pp": r["lo_pp"], "hi_pp": r["hi_pp"], "p": p_value(r["effect_pp"], se),
                         "vs_warm_pp": diff, "vs_warm_lo_pp": diff - fs.Z95 * se_d, "vs_warm_hi_pp": diff + fs.Z95 * se_d})
    q = fs.benjamini_hochberg(np.array([r["p"] for r in rows]))
    for r, qq in zip(rows, q):
        r["q"] = float(qq)
    return rows


def selection(df: pd.DataFrame, ends: pd.DataFrame) -> dict:
    m = df.merge(ends[["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "stint_sec_check", "sec_to_end", "end_reason"]],
                 on=["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID"], how="left")
    match = float((np.abs(m.stint_sec_check - m.stint_minutes * 60) < 1).mean())
    m["end_reason"] = m.end_reason.fillna("unknown")
    reasons = m.end_reason.value_counts()
    long_share = m[m.stint_minutes >= LONG].end_reason.value_counts(normalize=True)
    exo = m[m.end_reason.isin(EXOGENOUS)]
    coach = m[~m.end_reason.isin(EXOGENOUS) & (m.end_reason != "unknown")]
    c_exo, c_coach = contrast_fe(exo), contrast_fe(coach)
    diff = c_exo["effect_pp"] - c_coach["effect_pp"]
    se_d = float(np.hypot(c_exo["se_pp"], c_coach["se_pp"]))
    # Does the coach pull a player right after a cold streak? If so, the drop sits in the last minutes
    # before the substitution (selection on recent misses) and disappears once they are left out.
    far = m.sec_to_end >= END_WINDOW * 60
    by_window = [{"group": g, "window": w, **contrast_fe(sub)}
                 for g, base in (("coach", coach), ("exogenous", exo))
                 for w, sub in ((f"last {END_WINDOW:g} min before the end", base[~far.loc[base.index]]),
                                (f"more than {END_WINDOW:g} min before the end", base[far.loc[base.index]]))]
    # Direct measure: shots in the last minutes before the stint ends vs. earlier, holding stint minutes fixed
    m["near_end"] = (~far).astype(float)
    near_end = []
    for g, base in (("coach", coach), ("exogenous", exo)):
        r = fs.fe_slope(m.loc[base.index], ["near_end", "stint_minutes"]).iloc[0]
        near_end.append({"group": g, "effect_pp": r.coef_pp, "lo_pp": r.lo_pp, "hi_pp": r.hi_pp, "n": int(r.n)})
    return {
        "stint_match_rate": match,
        "reasons": [{"reason": k, "n": int(v), "share_long": float(long_share.get(k, 0.0))} for k, v in reasons.items()],
        "exogenous": {"label": "Ended by halftime/end of game or foul trouble", **c_exo, "slope": slope_warm(exo)},
        "coach": {"label": "Ended by the coach (substitution, timeout, between quarters)", **c_coach, "slope": slope_warm(coach)},
        "period_end_only": {"label": "Ended by halftime/end of game only", **contrast_fe(m[m.end_reason == "period_end"])},
        "all": {"label": "All stints (main analysis)", **contrast_fe(m)},
        "diff_pp": diff, "diff_lo_pp": diff - fs.Z95 * se_d, "diff_hi_pp": diff + fs.Z95 * se_d,
        "diff_p": p_value(diff, se_d), "end_window_min": END_WINDOW, "by_window": by_window, "near_end": near_end,
    }


def bench_time(df: pd.DataFrame, ends: pd.DataFrame) -> dict:
    """Does the cold start grow with the time spent on the bench before entering?"""
    m = fs.add_dev(df).merge(ends[["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID", "bench_sec"]],
                             on=["GAME_ID", "GAME_EVENT_ID", "PLAYER_ID"], how="left")
    m = m[m.bench_sec.notna()]
    cats = [("First stint of the game", m.bench_sec == FIRST_ENTRY), ("Halftime (3rd quarter start)", m.bench_sec == HALFTIME)]
    cats += [(lab, (m.bench_sec >= lo * 60) & (m.bench_sec < hi * 60)) for lo, hi, lab in BENCH_BUCKETS]
    rows = []
    for lab, mask in cats:
        sub = m[mask.values]
        r30 = fs._cluster_mean(sub[sub.stint_minutes < 0.5])
        r2 = fs._cluster_mean(sub[sub.stint_minutes < 2])
        se = (r30["hi_pp"] - r30["lo_pp"]) / (2 * fs.Z95) if r30["effect_pp"] is not None else None
        rows.append({"label": lab, "n_30s": r30["n"], "effect_30s_pp": r30["effect_pp"], "lo_30s_pp": r30["lo_pp"],
                     "hi_30s_pp": r30["hi_pp"], "n_2min": r2["n"], "effect_2min_pp": r2["effect_pp"],
                     "lo_2min_pp": r2["lo_pp"], "hi_2min_pp": r2["hi_pp"],
                     "p": p_value(r30["effect_pp"], se) if se else 1.0})
    q = fs.benjamini_hochberg(np.array([r["p"] for r in rows]))
    for r, qq in zip(rows, q):
        r["q"] = float(qq)
    # Continuous: change in the first-2-min deviation per minute on the bench (re-entries during play only)
    re = m[(m.bench_sec > 0) & (m.stint_minutes < 2)].copy()
    re["bench_min"] = re.bench_sec / 60.0
    s = fs.fe_slope(re, ["bench_min", "stint_minutes"]).iloc[0]
    return {"buckets": rows, "slope_pp_per_bench_min": {"coef_pp": s.coef_pp, "lo_pp": s.lo_pp, "hi_pp": s.hi_pp, "n": int(s.n)}}


def team_audit(df: pd.DataFrame, rng) -> dict:
    """Points lost to the cold start per team and season, game-bootstrap CI and empirical-Bayes shrinkage."""
    d = fs.add_dev(df)
    d = d[d.stint_minutes < 2].copy()
    d["pts"] = d.dev * np.where(d.SHOT_TYPE == "3PT Field Goal", 3.0, 2.0)
    d["jump"] = (d.SHOT_TYPE == "3PT Field Goal") | (d.SHOT_ZONE_BASIC == "Mid-Range")
    league_jump = float(d.jump.mean())
    rows = []
    for (tid, sea), g in d.groupby(["TEAM_ID", "SEASON"]):
        per = g.groupby("GAME_ID").pts.sum().values
        boot = per[rng.integers(0, len(per), size=(N_BOOT, len(per)))].sum(axis=1)
        rows.append({"team_id": int(tid), "team": g.TEAM_NAME.mode().iloc[0], "season": str(sea), "n_cold": int(len(g)),
                     "pts": float(per.sum()), "lo": float(np.percentile(boot, 2.5)), "hi": float(np.percentile(boot, 97.5)),
                     "se": float(boot.std()), "jump_share": float(g.jump.mean())})
    t = pd.DataFrame(rows)
    # shrink each season's team estimates toward that season's league mean (method of moments)
    t["shrunk"] = np.nan
    for sea, g in t.groupby("season"):
        mu = g.pts.mean()
        tau2 = max(0.0, g.pts.var() - (g.se ** 2).mean())
        t.loc[g.index, "shrunk"] = mu + tau2 / (tau2 + g.se ** 2) * (g.pts - mu)
        t.loc[g.index, "rank"] = g.pts.rank(ascending=False, method="min")  # 1 = loses the least
        t.loc[g.index, "tau"] = np.sqrt(tau2)
    r = float(np.corrcoef(t.jump_share, t.pts)[0, 1])
    return {"league_jump_share": league_jump, "corr_jump_share_pts": r,
            "rows": t.drop(columns="se").to_dict("records"),
            "tau_by_season": t.groupby("season").tau.first().to_dict()}


def free_throws(fts: pd.DataFrame) -> dict:
    f = fts[~fts.stint_inferred.astype(bool)].copy()
    f["stint_minutes"] = f.stint_seconds / 60.0
    f["SHOT_MADE_FLAG"] = f.made.astype(float)
    f["shot_residual"] = f.SHOT_MADE_FLAG  # no difficulty to discount: the player-season mean is the baseline
    f["SEASON"] = f.SEASON.astype(str)
    return {"n": int(len(f)), "n_inferred": int(fts.stint_inferred.astype(bool).sum()), "ft_pct": float(f.made.mean()),
            "players": int(f.PLAYER_ID.nunique()), "contrast": contrast_fe(f), "slope": slope_warm(f),
            "cold": cold_rows(f), "n_long": int((f.stint_minutes >= LONG).sum())}


def main():
    rebuild = "--rebuild" in sys.argv
    rng = np.random.default_rng(0)
    print("Reading", SRC)
    df_all = pd.read_csv(SRC, low_memory=False, dtype={"SEASON": str})
    df_all["is_home"] = df_all.is_home.astype(float)
    games = df_all[["TEAM_ID", "GAME_ID", "GAME_DATE"]].drop_duplicates().copy()
    games["date"] = pd.to_datetime(games.GAME_DATE.astype(str), format="%Y%m%d")
    games = games.sort_values(["TEAM_ID", "date"])
    games["b2b"] = (games.groupby("TEAM_ID").date.diff().dt.days <= 1).astype(float)
    df_all = df_all.merge(games[["TEAM_ID", "GAME_ID", "b2b"]], on=["TEAM_ID", "GAME_ID"], how="left")
    df_all["b2b"] = df_all.b2b.fillna(0.0)
    df = df_all[~df_all.stint_inferred].copy()

    print("Impact in points and wins...")
    imp = impact(df, rng)
    c = imp["cold"]["total"]
    print(f"   cold start: {c['pts']:.1f} pts/team-season [{c['lo']:.1f}, {c['hi']:.1f}]; "
          f"formula check {imp['cold']['formula_pts']:.1f}; b2b {imp['b2b']['pts']:.1f} [{imp['b2b']['lo']:.1f}, {imp['b2b']['hi']:.1f}]")

    print("Cold start by shot type...")
    types = by_shot_type(df)
    for r in types:
        print(f"   {r['type']:<22} {r['window']:<8} n={r['n']:>7} {r['effect_pp']:+.2f} [{r['lo_pp']:+.2f}, {r['hi_pp']:+.2f}] q={r['q']:.3g}")

    ends, fts = play_by_play_pass(rebuild)
    print("Selection bias (how stints end)...")
    sel = selection(df, ends)
    print(f"   stint match rate {sel['stint_match_rate']:.4f}; exogenous {sel['exogenous']['effect_pp']:+.2f} "
          f"[{sel['exogenous']['lo_pp']:+.2f}, {sel['exogenous']['hi_pp']:+.2f}] n_long={sel['exogenous']['n_long']}; "
          f"coach {sel['coach']['effect_pp']:+.2f} [{sel['coach']['lo_pp']:+.2f}, {sel['coach']['hi_pp']:+.2f}]")
    for r in sel["by_window"]:
        print(f"   {r['group']:<10} {r['window']:<32} {r['effect_pp']:+.2f} [{r['lo_pp']:+.2f}, {r['hi_pp']:+.2f}] n_long={r['n_long']}")
    for r in sel["near_end"]:
        print(f"   {r['group']:<10} last {END_WINDOW:g} min vs earlier     {r['effect_pp']:+.2f} [{r['lo_pp']:+.2f}, {r['hi_pp']:+.2f}]")

    print("Bench time before entering...")
    bench = bench_time(df, ends)
    for r in bench["buckets"]:
        print(f"   {r['label']:<30} n30={r['n_30s']:>6} {r['effect_30s_pp'] if r['effect_30s_pp'] is None else round(r['effect_30s_pp'], 2)} q={r['q']:.3g}")
    print("   slope per bench minute:", {k: round(v, 3) for k, v in bench["slope_pp_per_bench_min"].items()})

    print("Team audit...")
    audit = team_audit(df, rng)
    print(f"   corr(jump-shot share, points) = {audit['corr_jump_share_pts']:.2f}; tau by season {audit['tau_by_season']}")

    print("Free throws...")
    ft = free_throws(fts)
    print(f"   {ft['n']:,} FTs, long-vs-warm {ft['contrast']['effect_pp']:+.2f} [{ft['contrast']['lo_pp']:+.2f}, "
          f"{ft['contrast']['hi_pp']:+.2f}]; cold 0-30 s {ft['cold'][0]['effect_pp']}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(clean({"impact": imp, "shot_type": types, "selection": sel, "free_throws": ft,
                         "bench_time": bench, "team_audit": audit}), fh, ensure_ascii=False)
    print("->", OUT)


if __name__ == "__main__":
    main()
