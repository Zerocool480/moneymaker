# Backtest Plan -- replay 2026

## Data
Owner archive: 10+ dated league workbooks + DataGolf CSVs (US Open, Travelers,
John Deere, Scottish, ISCO, Puntacana, The Open, 3M, Rocket, Wyndham, BMW).
Layout: data/2026/league/<date>.xlsx, data/2026/datagolf/<event>.csv.

## Harness (mm backtest --season 2026)
Per event, using ONLY information available at that pick deadline:
load nearest-prior workbook -> run board + sequencer -> record engine pick vs
actual pick vs realized earnings -> run race sim, store predicted P vs outcome.

## Acceptance
- SumEV(engine) >= SumEV(actual); realized comparison reported, not gating.
- The five 2026 "saves" reproduce mechanically:
  1. John Deere: trailing tie-break -> Gotterup (won $1.584M).
  2. ISCO: Koivun ranked #1 and NOT amateur-flagged (pro as of John Deere).
  3. The Open: correlation logic -> Hovland; beats Hatton+Kim by >=4 pts P(win).
  4. BMW: Fox rejected (~40/50 grade) despite reserved-ace status;
     Thorbjornsen tier surfaces on top.
  5. Wyndham: expiring Bradley (#7 EV) not auto-picked; English on top.
- Calibration: weekly P(pass) vs observed -- Brier reported; no bucket >15 pts
  miscalibrated across the season.
- Documented limitations reproduce as such (Clark US Open ~1% model win; Fox
  Open win): the engine sells EV + risk accounting, not prophecy.

## Regression
Freeze replay outputs as golden files; future math changes diff intentionally.
