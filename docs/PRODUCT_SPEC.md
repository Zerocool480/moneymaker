# Money Maker Engine — Product Spec (v1)

## 1. Problem
One-and-done golf is a season-long resource-allocation game. 2026 proved the
edges, in dollar order:
1. Pool intelligence — knowing every rival's remaining golfers beats knowing golf.
2. EV-ranked best-available — DataGolf probabilities x payout ladder x unused list.
3. Sequencing — whole-season assignment beats greedy weekly picking; never spend
   a playoff-eligible ace at a weak event.
4. Race simulation — P(win/cash) with per-rival threat decomposition.
5. Opponent modeling — rivals are predictable (chalk, form-chasing, mirroring);
   5/8 picks called in one measured 2026 week.

## 2. User & cadence
Single user. Weekly: upload sheet -> pull preds -> lock pick (<=5 min). Sunday:
live threat card. January: full-season plan before the Sony.

## 3. MVP features (all validated manually in 2026)
- F1 League sheet ingestion (xlsx; contract in DATA_MODEL.md).
- F2 Predictions ingestion (CSV now, API phase 2).
- F3 Best-available board per manager x event: EV/win%/cut%, RESERVED guard,
  eligibility flags (amateur/LIV/field/playoff-bubble).
- F4 Season sequencer (assignment optimization; ALGORITHMS section 6).
- F5 Race Monte Carlo across remaining events, both boards, shared-golfer
  correlation, per-rival P(pass), scenario conditionals, sensitivity band.
- F6 Final-round strokes simulator ("Saturday night mode"; ALGORITHMS section 5).
- F7 Threat board + Sunday card with dollar pass-thresholds.
- F8 Opponent tendency profiles from full pick history.
- F9 Week journal (auto-log results, gaps, rationale).

## 4. Non-goals (v1)
Accounts, payments, league hosting, betting anything, mobile.

## 5. Success criteria
- Backtest parity (BACKTEST_PLAN acceptance list, incl. the five 2026 "saves").
- <=5-minute weekly workflow; season plan generated before Sony.

## 6. Screens (phase 4)
Dashboard (standings/gaps/plan). Pick screen (board + why-panel + predicted
rival picks). Season map (calendar x assignment, drag-override). Race odds
(distributions, threat table, sensitivity toggles). Sunday card. History.

## 7. Stack
Python 3.12, SQLite, pandas/numpy/scipy, FastAPI, HTMX/simple React,
APScheduler. Local-first; VPS optional later.
