# CLAUDE.md — Money Maker Engine

## What this is
A personal analytics engine for a one-and-done fantasy golf league ("Money Maker",
~86 managers). The owner (Jay) ran the entire 2026 season manually with an AI
assistant and finished in the money in both segment and overall races. This repo
is the productization of that proven workflow. Every algorithm in docs/ALGORITHMS.md
was validated live during the 2026 season — do not "improve" the math without
running docs/BACKTEST_PLAN.md first.

## League rules (encode these — they are the product)
- One-and-done: each MANAGER may use each golfer once per SEASON (not per segment).
  Different managers may pick the same golfer the same week.
- One pick per event; MAJORS get TWO picks (two adjacent sheet columns).
- Scoring: pick's actual PGA Tour prize money adds to the manager's balance.
- Season = 4 segments. Segment prizes (2026: 750/400/250) + season-long OVERALL
  prizes (2026: 4000/2200/1500/1000/700/400 top 6). Overall >> segment.
- Eligibility traps (all occurred in 2026):
  - AMATEURS earn $0 regardless of finish (flag "(a)"; re-verify weekly —
    Koivun flipped amateur-to-pro mid-season and became a correct pick).
  - LIV golfers: majors only; BARRED from FedEx playoffs (a hoarded Rahm
    expired unplayable at the BMW).
  - Playoff events: exclusive fields (top-70 St. Jude, top-50 BMW), NO CUT.
  - Check WDs/commitments on lock day.

## Build phases (in order)
1. Core lib (src/moneymaker/) — season-proven logic ships here. Wire it, add
   tests, make cli.py work end-to-end (data formats: docs/DATA_MODEL.md).
2. DataGolf API client (https://datagolf.com/api-access; ~$30/mo). Keep CSV
   fallback — CSV columns == API preds shape.
3. Backtest harness — replay 2026 per docs/BACKTEST_PLAN.md.
4. Local web UI (FastAPI + HTMX or simple React) — screens in PRODUCT_SPEC §6.
5. LATER: multi-manager sharing. Not MVP.

## Non-negotiables
- names.norm is the backbone; every join goes through it.
- Shared golfers across managers share the SAME simulation draw (correlation).
- Integer strokes + tie-averaged ladders in the strokes simulator.
- Analytics only. No betting integrations, ever (owner works for a sportsbook).

## Target CLI (phase 1)
mm ingest-league data/league/latest.xlsx
mm ingest-preds data/datagolf/EVENT.csv   |  mm fetch-preds --event ID
mm best-available --manager "Jay Doura" --event EVENT [--posture leading|trailing]
mm sequence --manager "Jay Doura"
mm simulate --board overall|segment --n 300000
mm threats --event EVENT
mm sunday-card
