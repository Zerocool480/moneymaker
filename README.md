# Money Maker Engine
One-and-done fantasy golf analytics: pool intelligence, EV boards, season
sequencing, race simulation, opponent modeling. Distilled from a full
manually-run 2026 season. Start with CLAUDE.md, then docs/.

Setup: `pip install -e . && pytest`

## Weekly workflow (~5 minutes)
```
mm ingest-league data/league/latest.xlsx --self "Jay Doura" --season 2027
mm ingest-preds data/datagolf/pga.csv --event "pga"     # or: mm fetch-preds
mm best-available --event "pga" --posture trailing
mm threats --event "pga"
# lock your pick, then Sunday:
mm sunday-card --positions data/live/positions.csv --event "pga"
```

## Planning & racing
```
mm sequence --reserve "Scheffler, Scottie"     # whole-season assignment
mm simulate --board overall --n 300000 --sensitivity
mm opponents                                   # rival tendency profiles
mm backtest --league-dir data/2026/league --preds-dir data/2026/datagolf
```

Housekeeping: `mm set-self`, `mm flag-liv "Rahm, Jon"`, `mm journal --add "..."`.
DB path: `--db` or `MM_DB` (default `data/moneymaker.db`). Season: `--season`
or `MM_SEASON` (defaults to the latest ingested season).
