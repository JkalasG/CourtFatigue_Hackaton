/* Bench calculator (web/js/calc.js): each term must reproduce the values written by the Python scripts.
   Usage: node tests/test_calculator.js */
const fs = require("fs");
const path = require("path");
const CALC = require("../web/js/calc.js");

const read = (f) => JSON.parse(fs.readFileSync(path.join(__dirname, "..", "web", "data", f), "utf8"));
const S = read("summary.json"), X = read("extra.json");
let n = 0, fail = 0;
function check(name, cond) {
  n++;
  if (!cond) { fail++; console.log("FAIL", name); }
}
const close = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol;

// 1. Cold-start term = the Python estimate for that shot type and window
const WIN = [[0, "0–30 s"], [29, "0–30 s"], [30, "30–60 s"], [59, "30–60 s"], [60, "1–2 min"], [119, "1–2 min"]];
for (const [k, label] of Object.entries(CALC.TYPES)) {
  for (const [sec, w] of WIN) {
    const row = X.shot_type.find((r) => r.type === label && r.window === w);
    const c = CALC.coldTerm(X, k, sec);
    check(`cold ${k} ${sec}s`, c.window === w && close(c.pp, row.effect_pp));
  }
  check(`no cold term from minute 2 (${k})`, CALC.coldTerm(X, k, 120).pp === 0 && CALC.coldTerm(X, k, 180).pp === 0);
}

// 2. Bench adjustment = that bucket's 0-30 s drop minus the overall 0-30 s drop, first 30 s only
const overall = S.cold_start.find((r) => r.label === "0–30 s").effect_pp;
const bucket = (lab) => X.bench_time.buckets.find((r) => r.label === lab).effect_30s_pp - overall;
check("bench 2 min", close(CALC.benchAdj(X, overall, "re", 2, 10).pp, bucket("< 3 min")));
check("bench 8 min", close(CALC.benchAdj(X, overall, "re", 8, 10).pp, bucket("6–10 min")));
check("bench 20 min", close(CALC.benchAdj(X, overall, "re", 20, 10).pp, bucket("> 15 min")));
check("first stint", close(CALC.benchAdj(X, overall, "first", 0, 10).pp, bucket("First stint of the game")));
check("halftime", close(CALC.benchAdj(X, overall, "half", 0, 10).pp, bucket("Halftime (3rd quarter start)")));
check("bench only in the first 30 s", CALC.benchAdj(X, overall, "re", 8, 45).pp === 0);

// 3. League make rate per type is a share-weighted mean of summary.json zones
const lg = CALC.leagueFg(S);
const rimW = S.zone_share["Restricted Area"] + S.zone_share["In The Paint (Non-RA)"];
check("league rim", close(lg.rim, (S.zone_share["Restricted Area"] * S.zone_fg["Restricted Area"] +
  S.zone_share["In The Paint (Non-RA)"] * S.zone_fg["In The Paint (Non-RA)"]) / rimW));
check("league ordering rim > mid, rim > three", lg.rim > lg.mid && lg.rim > lg.three);

// 4. Shot classification on the court geometry (tenths of a foot, rim at 0,0)
check("corner three", CALC.classify(225, 20) === "three");
check("top three", CALC.classify(0, 260) === "three");
check("layup", CALC.classify(5, 10) === "rim");
check("elbow jumper", CALC.classify(90, 150) === "mid");

// 5. Player level: shrinkage toward the league with K shots
const shots = { x: [0, 0, 0, 0], y: [10, 10, 10, 10], m: [1, 1, 1, 0] };
const base = CALC.playerBase(shots, lg);
check("shrinkage", close(base.rim.p, (3 + CALC.K_SHRINK * lg.rim) / (4 + CALC.K_SHRINK)) && base.three.n === 0 && close(base.three.p, lg.three));

// 6. predict() adds the terms and the interval contains the estimate
const rival = { effect_pp: -1, lo_pp: -2, hi_pp: 0 };
const r = CALC.predict({ base, type: "three", X, overall30: overall, situation: "re", benchMin: 8, sec: 10, rival });
const expect = base.three.p + (-1 + CALC.coldTerm(X, "three", 10).pp + bucket("6–10 min")) / 100;
check("predict adds the terms", close(r.p, expect, 1e-12));
check("interval contains estimate", r.lo < r.p && r.p < r.hi);
const r2 = CALC.predict({ base, type: "three", X, overall30: overall, situation: "re", benchMin: 8, sec: 150, rival: null });
check("warmed up = player's level", close(r2.p, base.three.p, 1e-12));

console.log(fail ? `${fail} of ${n} checks FAILED` : `OK: ${n} checks`);
process.exit(fail ? 1 : 0);
