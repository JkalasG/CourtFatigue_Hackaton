## Inspiration

Every basketball fan has heard it: *a tired player can't shoot.* Legs go, the release gets flat, and the ball starts hitting the front of the rim. I believed it too. It is one of those ideas that feels so obvious nobody checks it, yet it shapes real decisions: coaches pull shooters "before they get tired", and fans blame missed shots on too many minutes.

So I decided to test it: **does a player's shooting accuracy drop the longer they stay on court without a rest?** I expected to confirm the old saying. The data told a different story: **the problem is not when a player leaves, but how they come in.**

## What it does

CourtFatigue measures how NBA shooting accuracy changes with **time on court**, after discounting how hard each shot was, and tells you **how certain** any claim about a specific player can be. The headline is the opposite of the myth:

- **Cold start:** in the first 30 seconds after checking in, players shoot **1.46 percentage points** below their normal level (95% CI −1.95 to −0.97), and are back to normal by minute 2. That costs each team about **27 points a season** (CI 19 to 36), roughly 0.9 wins.
- **It replicated.** I wrote down the plan, the frozen estimates and the success rule **before** downloading the 2025-26 season, which the analysis had never seen. Result: **−1.35 pp** (CI −2.24 to −0.46). Replicated.
- **No shooting fatigue** up to ~12 consecutive minutes (+0.21 pp, CI −0.13 to +0.56), also in 2025-26 (+0.31). **0 of 592** players show a provable drop.
- **Back-to-backs** cost 0.39 pp (about 12 points a season); home court adds 0.38 pp.

The web app has five tabs:

- **Summary:** the answer in plain language, four key numbers and the placebo test that shows why a popular coaching rule is noise.
- **For the coach:** a one-page, printable card with four findings, four actions and the evidence behind each one, plus how a staff can use it and what it does *not* do.
- **Tools:**
  - **Bench calculator:** the expected make probability of the next shot, depending on the player, how they came in (re-entry, first entry, after halftime), seconds on court, shot type and rival.
  - **Check players:** any player's curve by minute, their rested vs. tired shot maps, and a verdict with its margin of error.
  - **New player:** a projection for a player with no history, with its uncertainty.
- **Evidence:** organised in three chapters: the cold start (replication, cost in points, shot type, free throws, bench time), the absence of fatigue (selection bias, robustness, season-by-season replication, court zones, player traits) and teams (audit of points lost per team, team defense).
- **3D simulation:** take a shot anywhere on the court and change the minutes, the rival team and the defender distance. Every term of the probability comes from measured data, and a panel shows **what weighs most** on that shot.

## How we built it

**Data.** 4 NBA regular seasons (2021-22 to 2024-25): 4,920 games and 872,158 shots with coordinates, plus the play-by-play with substitutions. The 2025-26 season (1,230 games, 219,156 shots) is used **only** for the preregistered replication. For the defender effect I used a separate public 2014-15 dataset (128,065 shots with defender distance, CC0).

**1. Rebuilding minutes on court.** The play-by-play logs substitutions but not who starts each quarter, so I reconstructed every player's stint: consecutive game-clock minutes on court at the moment of each shot. The counter carries over from Q1 to Q2 and from Q3 to Q4, and resets at halftime. Only ~0.3% of shots had an uncertain stint, and I excluded them.

**2. Discounting shot difficulty (xShot).** A gradient-boosting model predicts the probability of a make from distance, location, zone, shot type, period and clock, *without* minutes or player identity. It was validated by game (log-loss 0.640 vs. 0.691 with no model, AUC 0.657, calibration error 0.17 pp) and on an unseen season (AUC 0.654). Each shot gets a residual:

    residual = made (1 or 0) − expected probability (xShot)

**3. Comparing each player with themselves**, long stints against warmed-up ones:

    Cⱼ = mean residual with ≥ 8 consecutive min − mean residual with 2–6 min

plus a league-wide slope with player fixed effects and player-clustered errors:

    residual = player's own level + β × consecutive minutes      β = +0.027 pp/min (95% CI −0.014 to +0.069)

**4. Not inventing tired players.** Individual contrasts are combined in a random-effects model (league mean μ, true spread between players τ, each player's standard error sⱼ), and each player is shrunk toward the league average:

    shrunk Cⱼ = w × Cⱼ + (1 − w) × μ,   where   w = τ² / (τ² + sⱼ²)

A player is flagged only if their 95% CI excludes zero **and** they survive a Benjamini-Hochberg false-discovery correction. A placebo test, with minutes shuffled within each player, checks that the method stays silent when there is nothing to find.

**5. Cost in points.** For every cold-start shot, the drop in accuracy is multiplied by the value of the shot (2 or 3 points), summed per team and season, and turned into wins with the usual rule of ~30 points of differential per win. A bootstrap over games gives the interval.

**6. Preregistered replication.** Before touching 2025-26 I committed the plan, the frozen estimates and the success rule to the repository. The 2025-26 play-by-play only exists in a newer format, so I wrote an adapter and validated it on 2024-25, where both formats exist: **99.66%** of shots get the same stint. The xShot model stayed frozen (trained only on 2021-25).

**7. The app.** Python (pandas, NumPy, scikit-learn) for the analysis; a bilingual (EN/ES) web app in plain HTML, CSS and JavaScript with hand-made SVG charts; and a Three.js 3D simulator whose probability is

    P(make) = player base + distance + defender + rival team + cold start − fatigue

The bench calculator uses the same logic: the player's level on that shot type (shrunk toward the league when they have few shots), plus the rival's defensive effect, plus the cold start measured for that shot type and moment, plus the bench-time adjustment.

## Challenges we ran into

- **Fatigue vs. warm-up.** My first comparison (8+ min vs. under 4) gave **+0.65 pp**, as if players got better when tired. It was the cold start hiding inside the baseline. Using warmed-up players (2-6 min) as the reference fixed it.
- **Missing substitutions between quarters.** The play-by-play does not record who comes in during breaks, so I had to infer who was already on court in each period.
- **A new data format for the replication.** The 2025-26 play-by-play changed format, and names were written differently (accents, initials). The adapter had to match 99.66% of shots on a season where I could check it before using it on the unseen one.
- **Too little data per player.** A player's typical standard error is ~5 pp, so the minimum detectable drop is about (1.96 + 0.84) × 5 ≈ **14 pp**. Instead of hiding this, the tool shows it for every player.
- **Selection bias.** Coaches decide who stays on court and pull players who look tired, which could hide fatigue. So I split stints by how they ended. In stints that ended for reasons unrelated to the coach (halftime, end of game, foul trouble) there is still no drop (+0.83 pp). In stints the coach ended, the last 2 minutes before the change are ~9 points below normal: coaches react to recent misses, not to minutes played. It is still association, not causation.
- **Mixing eras.** The defender-distance data comes from 2014-15, so the simulator labels it as an association measured in another era, relative to the typical defender distance for each shot type, so it is not double-counted.

## Accomplishments that we're proud of

- **A finding that held up on unseen data.** The cold start replicated in a preregistered test on 2025-26 (−1.35 pp), with the plan committed before downloading the season. The result could have failed; it did not.
- **Turning it into points.** About **27 points per team and season**, almost one win, which is the language a coach uses.
- **Showing where it hurts:** the drop is 2-3 times larger in threes (−1.8 pp) and mid-range (−2.6 pp) than at the rim (−0.8 pp), and it appears even in **free throws** (−1.9 pp), where there is no defender.
- **Reporting the nulls honestly.** The drop does not grow with time on the bench (−0.04 pp per minute, CI −0.12 to +0.03): it is entering the game's rhythm, not cooling down. And teams do not differ from each other beyond noise (between-team spread τ = 0 in all four seasons), so the team audit is not sold as a ranking.
- **Turning a "null" result into a useful one:** fatigue is **pinned down** (+0.21 pp after 8+ minutes, CI −0.13 to +0.56), not just "not significant".
- **Showing that a common coaching rule is noise:** *"bench them if they drop 3 points"* flags **60.5%** of players with real data and **59.4%** with random minutes. Our method flags **0%** and **0.04%**.
- **0 of 592** players labelled "the one who gets tired". The tool says what it can and cannot tell instead of inventing a number.
- **Tools a coach can use:** a printable one-page card, a bench calculator and a 3D simulator built from data, not hand-written formulas.
- Full **reproducibility:** re-running the pipeline from a clean copy of the repo, following the README, gives exactly the same results, and the tests check the calculator, the statistics and the simulator.

## What we learned

- **A result that looks like fatigue is often just noise.** Without a placebo test and a multiple-comparison correction, you will always find "tired" players.
- **The baseline matters as much as the model.** Choosing the wrong reference turned a cold start into a fake "fatigue benefit".
- **Writing the prediction down first changes everything.** Preregistering the replication removed any temptation to adjust the analysis after seeing the result.
- **Honesty is a feature.** Saying "we can only detect drops of ~14 pp for this player" or "teams do not differ beyond noise" is more useful to a coach than a confident number.
- The old saying isn't exactly wrong, it's incomplete: the players coaches keep on the floor don't shoot worse, which suggests current rotations already avoid the problem. **The risk is not when a player leaves, but how they come in.**

## What's next for CourtFatigue

- **Testing the fix:** whether a "rhythm first play" after a substitution (a cut or drive instead of a first three) and activating the sub before they check in actually reduce the cold start. The 27 points are the full cost; how much a coach can win back has not been tested.
- **Player-tracking data** for recent seasons, so defender distance can enter the main model instead of coming from another era.
- **Physical load:** minutes over previous games, travel and rest days, and biometrics where available.
- **Beyond shooting:** does the cold start or fatigue show up in defense, rebounding or turnovers?
- **Injuries:** cross consecutive minutes and back-to-backs with public injury reports.
- **Keep replicating:** add 2026-27 when it is available, with the same preregistered rule.

## Built with

Python, pandas, NumPy, scikit-learn, HTML, CSS, JavaScript, SVG, Three.js, NBA Stats API play-by-play and shot data (2021-22 to 2025-26), NBA shot logs 2014-15 (CC0).
