# Data Model

## SQLite schema (v1)
golfers(golfer_id PK, key UNIQUE, display_name, is_liv, is_amateur,
        turned_pro_date)
  -- is_amateur added in v1 implementation: current "(a)" flag from the
  -- latest preds pull; turned_pro_date is stamped when the flag flips off
  -- (the Koivun mechanic) and the golfer is a pro forever after.
managers(manager_id PK, name UNIQUE, is_self)
events(event_id PK, season, name, segment, seq, purse, picks_per_manager,
       has_cut, field_type[open|signature|major|playoff70|playoff50|opposite],
       datagolf_event_id)
picks(season, event_id, manager_id, slot, golfer_id, earnings NULL-until-settled,
      PK(season,event_id,manager_id,slot))
predictions(event_id, golfer_id, pulled_at, win, top5, top10, top20, make_cut,
      source, PK(event_id,golfer_id,pulled_at))
field_entries(event_id, golfer_id, status[committed|wd|alternate])
standings_snapshots(season, taken_at, manager_id, board[overall|segmentN], total)
journal(id PK, season, event_id, entry_at, kind, body)

Derived, never stored: used set (manager's season picks); available pool =
field - used - ineligible (amateur-before-pro-date, LIV-outside-majors,
playoff-non-qualifier).

## League sheet contract (2026 format, proven across 10 uploads)
Tabs used: Selections, Standings, Money Earned. IGNORE per-tournament tabs --
they hold PRIOR-YEAR reference results, not current scoring (verified 2026-07).

Selections / Money Earned layout:
- Row 0 header. Col 0 = manager name. One column per event titled like
  "Rocket Classic- $10M" (parse purse from suffix). MAJORS = TWO adjacent
  columns, same title. Segment boundaries = marker columns "Segment N" (skip).
- Cells are display names, sometimes "(WD)"-annotated; strip parentheticals,
  the pick still consumes the golfer.

Standings: overall = cols (1,2); segments = (6,7),(8,9),(10,11),(12,13).

## DataGolf contract
CSV columns: player_name ("Last, First"), sample_size, win, top_5, top_10,
top_20, make_cut (probabilities). No-cut events: make_cut==1.0 for all rows --
use to auto-detect has_cut. API preds map 1:1; field-updates fills
field_entries; live stats power the Sunday card.
