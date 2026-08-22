# Algorithms (all live-validated, 2026)

## 1. Name normalization (names.norm)
"Last, First" -> "first last"; lowercase; fold o-slash/e-acute/a-ring/umlauts;
strip parentheticals and non-alpha. Every join uses this key. Hazards covered by
tests: Hojgaard, Aberg, Si Woo vs Tom Kim, the Fitzpatrick brothers.

## 2. Payout ladders (payouts.py)
Position payout = purse x standard PGA fraction vector (.18, .109, .069, ..., 50
slots). Ties split covered slots evenly. Majors use announced ladders when known
(2026 Open: $17.75M / $3.2M winner).

## 3. Bucket EV engine (ev.py)
Buckets from marginals: W=win; solo2=(t5-w)x0.30; 3-5=(t5-w)x0.70; 6-10=t10-t5;
11-20=t20-t10; 21-40=(cut-t20)x0.55; 41-cut=(cut-t20)x0.45; MC=1-cut.
EV = sum p x payout(mid-range). Splits sensitivity-tested (+-.05 -> <0.2pt on
season P(win)). Two sort modes: leading (EV/floor) vs trailing (win%-blended).

## 4. Race Monte Carlo (simulate.py: SharedDraws + bucket_draw)
Bucket draws per golfer per event; correctness rules that matter:
- SHARED DRAWS: same golfer across managers = one draw per trial (mirror picks
  cancel; same-golfer threats correlate -- the 2026 "Clark riders" effect).
- EXCLUSIVE CHAMPION: one categorical winner draw over tracked win probs +
  rest-of-field; non-winners use conditional (no-W) curves. Runner-up likewise
  with TRUE marginals (sum of solo2 ~= .15; forcing a larger share once inflated
  threats by 3 points -- keep a regression test on this).
- Finish = 1 + count(strictly ahead). Report P(pass) per rival, P(finish=k),
  conditionals, and a sensitivity band (splits +-, key-rival win +-50%).

## 5. Final-round strokes simulator (simulate.strokes_final_round)
Inputs: 54-hole to-par, pre-tournament win probs.
sg_i = 0.62 x (ln w_i - mean ln w)  (best player ~= -1.6 strokes/round).
R4 = round(-sg_i + eps), eps ~ Student-t(df=8) scaled to sd ~= 2.85 -> INTEGER
strokes -> realistic tie frequency. Totals sorted per trial; tie groups share
the ladder via cumulative-sum group means (vectorized, no Python loop).
Outputs: exact finish/cash distributions, dollar pass-thresholds ("needs
solo-7th ~= $655k"), conditionals. This mode found ~8 points of risk the bucket
model missed: a T6 with better players stacked behind is fragile -- median
finish is not current position. Sensitivity: sd in [2.6, 3.1], normal vs t,
skill on/off.

## 6. Season sequencer (sequencer.py)
A[golfer,event] availability x V[golfer,event] EV. Choose one per slot, all
distinct, max sum V: brute force top-k(=8)/event or Hungarian. Constraints:
- RESERVED playoff-eligible aces excluded from weak fields (the late $20M
  no-cut pair was ~57% of remaining purse in 2026).
- Expiring != must-play (Bradley lesson): play an expiring name only if best.
- Posture tie-break: trailing -> win%, leading -> floor (the Gotterup John
  Deere call that won Segment 3).
- Correlation bonus when defending: matching a chaser's best available card
  neutralizes it (Hovland at The Open ~= +6 points of P(win)).

## 7. Opponent model (opponents.py)
Mine per-rival: chalk rate, form-chasing rate, mirror-vs-self rate, hoard
tendency, weak-event effort. Predict pick = argmax over their board weighted by
profile (2026: 5/8 correct in the measured week). Feed predictions into
cancellation/threat pre-computation.

## 8. Eligibility & traps (league.py rules)
Amateur -> $0 (loud flag; re-verify weekly). LIV: majors-only, playoff-barred;
flag rivals' dead hoards. Playoff bubbles: pull projected top-70/50 before the
Wyndham; reserved names outside the bubble convert to spend-now. WD check at
lock ("(WD)" cells still consume the pick).
