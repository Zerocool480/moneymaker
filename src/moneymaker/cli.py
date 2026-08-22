"""mm — Money Maker Engine CLI (phase 1).

Weekly cadence: mm ingest-league -> mm ingest-preds (or fetch-preds) ->
mm best-available -> lock pick. Sunday: mm sunday-card. Planning: mm sequence,
mm simulate, mm threats, mm opponents. Replay: mm backtest.
"""
import datetime as _dt
import os

import numpy as np
import pandas as pd
import typer

from . import backtest as backtest_mod
from . import opponents as opp
from . import race as race_mod
from . import store
from .datagolf import DataGolfAPI, load_preds_csv
from .ev import board as ev_board
from .payouts import ladder
from .sequencer import solve as seq_solve
from .simulate import strokes_final_round

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="One-and-done fantasy golf analytics engine.")

DB_OPT = typer.Option(None, "--db", envvar="MM_DB", help="SQLite path")
SEASON_OPT = typer.Option(None, "--season", envvar="MM_SEASON")
STRONG_FIELDS = {"major", "playoff70", "playoff50", "signature"}


def _conn(db):
    return store.connect(db)


def _season(conn, season):
    if season:
        return int(season)
    row = conn.execute("SELECT MAX(season) FROM events").fetchone()
    return int(row[0]) if row and row[0] else _dt.date.today().year


def _self(conn) -> str:
    name = store.self_manager(conn)
    if not name:
        typer.echo("No self manager set: use --self on ingest-league or "
                   "`mm set-self NAME`.")
        raise typer.Exit(1)
    return name


def _money(x):
    return f"${x:,.0f}" if pd.notna(x) else "-"


def _pct(x):
    return f"{100 * x:.1f}%"


def _purse_of(erow) -> float:
    p = erow["purse"]
    if p is None or (isinstance(p, float) and np.isnan(p)) or p <= 0:
        typer.echo(f"WARNING: no purse parsed for {erow['name']}; assuming $10M.")
        return 1e7
    return float(p)


def _remaining(conn, season, segment=None) -> list:
    """Events with predictions and no settled earnings yet, in seq order."""
    out = []
    for eid in store.events_with_preds(conn, season):
        erow = conn.execute("SELECT * FROM events WHERE event_id=?",
                            (eid,)).fetchone()
        if segment and erow["segment"] != segment:
            continue
        settled = conn.execute(
            "SELECT COUNT(*) FROM picks WHERE season=? AND event_id=? AND "
            "earnings IS NOT NULL", (season, eid)).fetchone()[0]
        if not settled:
            out.append(erow)
    return out


def _plans(conn, season, event_rows, profiles=None):
    """event name -> {manager: [keys]}; locked picks verbatim, projections
    (opponent model) for everyone else. Projections consume the golfer for
    later events (one-and-done). Returns (plans, curves, purses, cuts)."""
    plans, curves, purses, cuts = {}, {}, {}, {}
    projected: dict[str, set] = {}
    for erow in sorted(event_rows, key=lambda r: r["seq"]):
        preds = store.latest_preds(conn, erow["event_id"])
        pred = opp.predicted_picks(conn, season, erow, preds, profiles,
                                   extra_used=projected)
        locked = store.event_picks(conn, season, erow["event_id"])
        plan = {}
        for mgr in store.managers_list(conn):
            if locked.get(mgr):
                plan[mgr] = locked[mgr]
            elif pred.get(mgr):
                plan[mgr] = pred[mgr]
                projected.setdefault(mgr, set()).update(pred[mgr])
        name = erow["name"]
        plans[name] = plan
        curves[name] = preds
        purses[name] = _purse_of(erow)
        cuts[name] = bool(erow["has_cut"])
    return plans, curves, purses, cuts


@app.command("ingest-league")
def ingest_league(path: str, season: int = SEASON_OPT,
                  self_name: str = typer.Option(None, "--self"),
                  db: str = DB_OPT):
    """Load a league workbook (Selections + Money Earned + Standings)."""
    conn = _conn(db)
    season = season or _dt.date.today().year
    s = store.ingest_league(conn, path, int(season), self_name)
    typer.echo(f"season {season}: {s['events']} events, {s['picks']} picks "
               f"({s['settled']} settled), {s['standings_rows']} standings rows.")


@app.command("set-self")
def set_self(name: str, db: str = DB_OPT):
    """Mark which manager is you."""
    conn = _conn(db)
    store.set_self(conn, name)
    typer.echo(f"self = {name}")


@app.command("ingest-preds")
def ingest_preds(path: str, event: str = typer.Option(None, "--event"),
                 season: int = SEASON_OPT, db: str = DB_OPT):
    """Load a DataGolf predictions CSV for one event."""
    conn = _conn(db)
    season = _season(conn, season)
    frag = event or os.path.splitext(os.path.basename(path))[0]\
        .replace("_", " ").replace("-", " ")
    erow = store.resolve_event(conn, season, frag)
    d = load_preds_csv(path)
    s = store.ingest_preds_frame(conn, d, erow["event_id"], "csv")
    ams = d.loc[d["amateur"], "player_name"].tolist()
    typer.echo(f"{erow['name']}: {s['rows']} golfers, has_cut={s['has_cut']}"
               + (f", AMATEURS: {', '.join(map(str, ams))}" if ams else ""))


@app.command("fetch-preds")
def fetch_preds(event: str = typer.Option(..., "--event"),
                tour: str = typer.Option("pga", "--tour"),
                season: int = SEASON_OPT, db: str = DB_OPT):
    """Pull pre-tournament predictions from the DataGolf API (needs
    DATAGOLF_API_KEY)."""
    conn = _conn(db)
    season = _season(conn, season)
    erow = store.resolve_event(conn, season, event)
    try:
        d = DataGolfAPI().pre_tournament_preds(tour)
    except RuntimeError as e:
        typer.echo(str(e))
        raise typer.Exit(1)
    s = store.ingest_preds_frame(conn, d, erow["event_id"], "api")
    typer.echo(f"{erow['name']}: {s['rows']} golfers from API, "
               f"has_cut={s['has_cut']}")


@app.command("flag-liv")
def flag_liv(names: list[str], clear: bool = typer.Option(False, "--clear"),
             db: str = DB_OPT):
    """Mark golfers as LIV members (majors-only, playoff-barred)."""
    conn = _conn(db)
    store.set_liv(conn, names, not clear)
    typer.echo(f"{'cleared' if clear else 'flagged'} LIV: {', '.join(names)}")


@app.command("best-available")
def best_available(manager: str = typer.Option(None, "--manager"),
                   event: str = typer.Option(..., "--event"),
                   posture: str = typer.Option("neutral", "--posture",
                                               help="leading|trailing|neutral"),
                   reserve: list[str] = typer.Option([], "--reserve"),
                   top: int = typer.Option(15, "--top"),
                   season: int = SEASON_OPT, db: str = DB_OPT):
    """EV-ranked board for one manager at one event (F3)."""
    conn = _conn(db)
    season = _season(conn, season)
    manager = manager or _self(conn)
    erow = store.resolve_event(conn, season, event)
    preds = store.latest_preds(conn, erow["event_id"])
    try:
        used = store.used_set(conn, season, manager)
    except KeyError as e:
        typer.echo(str(e))
        raise typer.Exit(1)
    inel = store.ineligible_keys(conn, erow, preds)
    reserved = {store.norm(r) for r in reserve}
    b = ev_board(preds, _purse_of(erow), used, has_cut=bool(erow["has_cut"]),
                 reserved=reserved, ineligible=set(inel), posture=posture)
    typer.echo(f"{erow['name']}  purse {_money(erow['purse'])}  "
               f"has_cut={bool(erow['has_cut'])}  preds {preds.attrs['pulled_at']}")
    typer.echo(f"{manager}: {len(used)} used, {len(b)} available, "
               f"{len(inel)} ineligible ({posture} posture)\n")
    view = b.head(top)[["display_name", "win", "top_5", "make_cut",
                        "exp", "floor", "score", "flags"]].copy()
    for c in ("win", "top_5", "make_cut"):
        view[c] = view[c].map(_pct)
    for c in ("exp", "floor", "score"):
        view[c] = view[c].map(_money)
    view.index = range(1, len(view) + 1)
    typer.echo(view.to_string())
    top_row = b.iloc[0] if len(b) else None
    if top_row is not None and top_row["reserved"]:
        typer.echo("\nGUARD: #1 is RESERVED for a strong field — confirm "
                   "before spending it here.")


def _is_strong(erow) -> bool:
    """Fields a RESERVED ace may be spent at. Explicit field_type wins;
    no-cut events (playoffs, signature no-cut) count as strong even when
    still typed 'open', so reserving an ace never bars him from the very
    events he is hoarded for."""
    return erow["field_type"] in STRONG_FIELDS or not erow["has_cut"]


@app.command("set-field-type")
def set_field_type(event: str, field_type: str,
                   season: int = SEASON_OPT, db: str = DB_OPT):
    """Tag an event: open|signature|major|playoff70|playoff50|opposite.
    Drives the reserved-ace guard and LIV playoff exclusion."""
    conn = _conn(db)
    season = _season(conn, season)
    erow = store.resolve_event(conn, season, event)
    try:
        store.set_field_type(conn, erow["event_id"], field_type)
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(1)
    typer.echo(f"{erow['name']}: field_type={field_type}")


@app.command("sequence")
def sequence(manager: str = typer.Option(None, "--manager"),
             top_k: int = typer.Option(8, "--top-k"),
             posture: str = typer.Option("neutral", "--posture",
                                         help="leading|trailing|neutral"),
             reserve: list[str] = typer.Option([], "--reserve"),
             events: str = typer.Option(None, "--events",
                                        help="comma-separated name fragments"),
             season: int = SEASON_OPT, db: str = DB_OPT):
    """Whole-season assignment over remaining OPEN slots (F4). Locked picks
    are pinned, majors get one slot per pick, reserved aces are barred from
    weak fields only, and posture shapes the scoring (s6)."""
    conn = _conn(db)
    season = _season(conn, season)
    manager = manager or _self(conn)
    if events:
        rows = [store.resolve_event(conn, season, f) for f in events.split(",")]
    else:
        rows = _remaining(conn, season)
    if not rows:
        typer.echo("No remaining events with predictions ingested.")
        raise typer.Exit(1)
    used = store.used_set(conn, season, manager)
    reserved = {store.norm(r) for r in reserve}

    boards, pinned = {}, {}
    for erow in rows:
        locked = store.event_picks(conn, season, erow["event_id"]).get(
            manager, [])
        slots = int(erow["picks_per_manager"] or 1)
        open_slots = slots - len(locked)
        for i, key in enumerate(locked):
            label = erow["name"] if slots == 1 else \
                f"{erow['name']} (slot {i + 1})"
            pinned[label] = key
        if open_slots <= 0:
            continue
        preds = store.latest_preds(conn, erow["event_id"])
        inel = store.ineligible_keys(conn, erow, preds)
        b = ev_board(preds, _purse_of(erow), used, has_cut=bool(erow["has_cut"]),
                     reserved=reserved, ineligible=set(inel), posture=posture)
        if not _is_strong(erow):
            b = b[~b["reserved"]]  # reserved aces excluded from WEAK fields
        pool = list(zip(b["score"].head(top_k), b["key"].head(top_k)))
        for s in range(open_slots):
            label = erow["name"] if slots == 1 else \
                f"{erow['name']} (slot {len(locked) + s + 1})"
            boards[label] = pool

    if not boards:
        typer.echo("Every remaining slot is already locked on the sheet.")
        raise typer.Exit(0)
    # Pinned keys are already excluded from every pool: locked picks are in
    # the manager's used set, so the plain Hungarian solve is safe.
    best = seq_solve(boards, top_k=top_k)
    if not best:
        typer.echo("No feasible distinct assignment found — widen --top-k.")
        raise typer.Exit(1)
    tot, asg = best

    defend = {}
    if posture == "leading":
        defend = _defend_marks(conn, season, rows, manager)
    typer.echo(f"{manager} — season plan, {len(boards)} open slot(s)"
               + (f" + {len(pinned)} locked" if pinned else "")
               + f" ({posture} scoring, plan EV {_money(tot)}):\n")
    for label, key in pinned.items():
        typer.echo(f"  {label:<44} {key:<24} (locked)")
    for label, pool in boards.items():
        key = asg[label]
        ev = dict((kk, vv) for vv, kk in pool).get(key, 0.0)
        mark = "  DEFEND✓" if key in defend.get(label.split(" (slot")[0], set()) \
            else ""
        typer.echo(f"  {label:<44} {key:<24} {_money(ev)}{mark}")
    if posture == "leading" and defend:
        typer.echo("\nDEFEND✓ = matches a top chaser's likely pick — "
                   "mirroring neutralizes their week (ALGORITHMS s6).")


def _defend_marks(conn, season, rows, self_name) -> dict:
    """event name -> set of keys the top chasers are likely to play.
    Annotation only — the correlation-when-defending bonus stays a human
    call in v1 (magnitude needs the backtest to calibrate)."""
    standings = store.latest_standings(conn, season, "overall")
    if not standings or self_name not in standings:
        return {}
    chasers = [m for m, _ in sorted(standings.items(), key=lambda kv: -kv[1])
               if standings[m] < standings[self_name]][:3]
    if not chasers:
        return {}
    profiles = opp.mine_profiles(conn, season)
    out = {}
    for erow in rows:
        preds = store.latest_preds(conn, erow["event_id"])
        pred = opp.predicted_picks(conn, season, erow, preds, profiles)
        out[erow["name"]] = {k for m in chasers for k in pred.get(m, [])}
    return out


@app.command("simulate")
def simulate_cmd(board: str = typer.Option("overall", "--board",
                                           help="overall|segment1..4"),
                 n: int = typer.Option(100_000, "--n"),
                 seed: int = typer.Option(1, "--seed"),
                 sensitivity: bool = typer.Option(False, "--sensitivity"),
                 key_rival: str = typer.Option(None, "--key-rival"),
                 season: int = SEASON_OPT, db: str = DB_OPT):
    """Race Monte Carlo across remaining events (F5): shared draws,
    exclusive champion, per-rival threat decomposition."""
    if board != "overall" and board not in {f"segment{i}" for i in range(1, 5)}:
        typer.echo("--board must be overall or segment1..segment4")
        raise typer.Exit(1)
    conn = _conn(db)
    season = _season(conn, season)
    self_name = _self(conn)
    segment = int(board[-1]) if board.startswith("segment") else None
    standings = store.latest_standings(conn, season, board)
    if not standings:
        standings = {m: 0.0 for m in store.managers_list(conn)}
        typer.echo("NOTE: no standings snapshot for this board — starting "
                   "everyone at $0.")
    rows = _remaining(conn, season, segment)
    if not rows:
        typer.echo("No remaining events with predictions — ingest preds first.")
        raise typer.Exit(1)
    typer.echo(f"Simulating {board}: {len(rows)} remaining event(s), "
               f"{len(standings)} managers, n={n:,} …")
    profiles = opp.mine_profiles(conn, season)
    plans, curves, purses, cuts = _plans(conn, season, rows, profiles)
    res = race_mod.simulate_race(standings, plans, curves, purses, cuts,
                                 self_name, n=n, seed=seed)
    typer.echo(f"\n{self_name} — P(1st) {_pct(res['p_first'])}   "
               f"P(top3) {_pct(res['p_top3'])}   P(top6) {_pct(res['p_top6'])}")
    typer.echo("Finish distribution: " + "  ".join(
        f"{k}:{_pct(v)}" for k, v in res["dist"].items() if v > 0.001))
    threats = sorted(res["passes"].items(), key=lambda kv: -kv[1])[:15]
    typer.echo("\nTop threats (P(finishes ahead of you)):")
    gap = {m: standings.get(m, 0) - standings.get(self_name, 0)
           for m, _ in threats}
    for m, p in threats:
        typer.echo(f"  {m:<28} {_pct(p):>7}   gap {_money(gap[m])}   "
                   f"sim-EV +{_money(res['ev_added'].get(m, 0))}")
    if sensitivity:
        kr = key_rival or (threats[0][0] if threats else None)
        band = race_mod.sensitivity_band(
            standings, plans, curves, purses, cuts, self_name,
            metric="p_first" if board == "overall" else "p_top3",
            key_rival=kr)
        lo, hi = band.pop("band")
        typer.echo(f"\nSensitivity ({'P(1st)' if board == 'overall' else 'P(top3)'},"
                   f" key rival {kr}): {_pct(lo)} – {_pct(hi)}")
        for sc, v in band.items():
            typer.echo(f"  {sc:<16} {_pct(v)}")


@app.command("threats")
def threats(event: str = typer.Option(..., "--event"),
            n: int = typer.Option(50_000, "--n"),
            season: int = SEASON_OPT, db: str = DB_OPT):
    """Threat board for one event (F7): locked/predicted rival picks and
    P(pass) if the event plays out (overall board)."""
    conn = _conn(db)
    season = _season(conn, season)
    self_name = _self(conn)
    erow = store.resolve_event(conn, season, event)
    standings = store.latest_standings(conn, season, "overall") or \
        {m: 0.0 for m in store.managers_list(conn)}
    profiles = opp.mine_profiles(conn, season)
    plans, curves, purses, cuts = _plans(conn, season, [erow], profiles)
    locked = store.event_picks(conn, season, erow["event_id"])
    res = race_mod.simulate_race(standings, plans, curves, purses, cuts,
                                 self_name, n=n)
    my = plans[erow["name"]].get(self_name, ["?"])
    typer.echo(f"{erow['name']} — you: {', '.join(my)} "
               f"({'locked' if locked.get(self_name) else 'projected'})\n")
    disp = dict(zip(curves[erow["name"]]["key"],
                    curves[erow["name"]]["display_name"]))
    rows_out = sorted(res["passes"].items(), key=lambda kv: -kv[1])[:20]
    for m, p in rows_out:
        picks = plans[erow["name"]].get(m, [])
        tag = "locked" if locked.get(m) else "proj"
        mirror = " MIRROR" if set(picks) & set(my) else ""
        names = ", ".join(disp.get(k, k) for k in picks) or "-"
        typer.echo(f"  {m:<28} {_pct(p):>7}   {names} ({tag}){mirror}")


@app.command("sunday-card")
def sunday_card(positions: str = typer.Option(None, "--positions",
                                              help="CSV: player_name,to_par"),
                live: bool = typer.Option(False, "--live",
                                          help="pull 54-hole positions from "
                                          "the DataGolf live feed"),
                tour: str = typer.Option("pga", "--tour"),
                event: str = typer.Option(..., "--event"),
                n: int = typer.Option(200_000, "--n"),
                sd: float = typer.Option(2.85, "--sd"),
                season: int = SEASON_OPT, db: str = DB_OPT):
    """Final-round strokes card (F6/F7): finish distribution, per-rival
    P(pass), dollar pass-thresholds. Standings are assumed PRE-event."""
    if bool(positions) == live:
        typer.echo("Pass exactly one of --positions CSV or --live.")
        raise typer.Exit(1)
    conn = _conn(db)
    season = _season(conn, season)
    self_name = _self(conn)
    erow = store.resolve_event(conn, season, event)
    purse = _purse_of(erow)
    if live:
        try:
            ls = DataGolfAPI().live_stats(tour)
        except RuntimeError as e:
            typer.echo(str(e))
            raise typer.Exit(1)
        rnd = pd.to_numeric(ls.get("stat_round"), errors="coerce").max()
        if pd.notna(rnd) and int(rnd) != 3:
            typer.echo(f"WARNING: live feed is at round {int(rnd)}, not 54 "
                       "holes — the final-round model assumes R4 hasn't "
                       "started.")
        ls["to_par"] = pd.to_numeric(ls["total"], errors="coerce")
        alive = ~ls["position"].astype(str).str.upper().isin(
            ("CUT", "WD", "DQ", "DNS"))
        pos_df = ls.loc[alive & ls["to_par"].notna(),
                        ["player_name", "to_par"]]
        typer.echo(f"live positions: {len(pos_df)} players "
                   f"({ls['event_name'].iloc[0]}, updated "
                   f"{ls['last_updated'].iloc[0]})")
    else:
        pos_df = pd.read_csv(positions)
    preds = store.latest_preds(conn, erow["event_id"])
    winp = dict(zip(preds["key"], preds["win"]))
    floor_wp = max(min(winp.values(), default=1e-3) * 0.5, 1e-4)
    pos54, wp = {}, {}
    for _, r in pos_df.iterrows():
        k = store.norm(r["player_name"])
        pos54[k] = int(r["to_par"])
        wp[k] = float(winp.get(k, floor_wp))
    pay, tot, players = strokes_final_round(pos54, wp, purse, n=n, sd=sd)
    amateurs = set(preds.loc[preds["amateur"].astype(bool), "key"]) \
        if "amateur" in preds.columns else set()
    for k in amateurs & set(pay):
        pay[k] = np.zeros(n)           # amateurs cash $0 regardless of finish

    standings = store.latest_standings(conn, season, "overall") or \
        {m: 0.0 for m in store.managers_list(conn)}
    picks = store.event_picks(conn, season, erow["event_id"])
    zero = np.zeros(n)
    totals = {}
    for m, start in standings.items():
        t = np.full(n, float(start))
        for k in picks.get(m, []):
            t = t + pay.get(k, zero)   # missed cut / not in field -> $0
        totals[m] = t
    am_holders = [(m, k) for m, ks in picks.items() for k in ks
                  if k in amateurs]
    for m, k in am_holders:
        typer.echo(f"NOTE: {m} holds AMATEUR {k} — $0 whatever he shoots.")
    if self_name not in totals:
        typer.echo(f"{self_name} not in standings.")
        raise typer.Exit(1)
    self_total = totals[self_name]
    mine = ", ".join(picks.get(self_name, ["-"]))
    typer.echo(f"{erow['name']} Sunday card — you: {mine}\n")
    ahead = np.zeros(n, np.int32)
    passes = {}
    for m, t in totals.items():
        if m == self_name:
            continue
        beat = t > self_total
        passes[m] = float(beat.mean())
        ahead += beat.astype(np.int32)
    finish = ahead + 1
    dist = {k: float((finish == k).mean())
            for k in range(1, len(standings) + 1)}
    typer.echo("Board finish: " + "  ".join(
        f"{k}:{_pct(v)}" for k, v in dist.items() if v > 0.005))

    lad = ladder(purse, len(players))
    self_start = float(standings[self_name])
    typer.echo("\nPass thresholds (rivals ahead of you now):")
    for m, start in sorted(standings.items(), key=lambda kv: -kv[1]):
        if m == self_name or start <= self_start:
            continue
        gap = start - self_start
        covers = np.where(lad > gap)[0]
        pos_txt = (f"needs solo-{covers.max() + 1} ≈ {_money(lad[covers.max()])}"
                   if len(covers) else "no solo finish covers the gap")
        p_pass = float((self_total > totals[m]).mean())
        typer.echo(f"  {m:<28} gap {_money(gap)}  ({pos_txt}; "
                   f"P(you pass) {_pct(p_pass)})")


@app.command("opponents")
def opponents_cmd(season: int = SEASON_OPT, db: str = DB_OPT):
    """Rival tendency profiles mined from pick history (F8)."""
    conn = _conn(db)
    season = _season(conn, season)
    profs = opp.mine_profiles(conn, season)
    if not profs:
        typer.echo("No pick history — ingest the league sheet first.")
        raise typer.Exit(1)
    typer.echo(f"{'manager':<28} {'chalk':>6} {'form':>6} {'mirror':>7} "
               f"{'hoard':>6} {'events':>7}  dead hoard")
    for p in sorted(profs.values(), key=lambda p: -p.mirror_rate):
        dead = ", ".join(p.dead_hoard) if p.dead_hoard else ""
        typer.echo(f"{p.manager:<28} {p.chalk_rate:>6.0%} "
                   f"{p.form_chase_rate:>6.0%} {p.mirror_rate:>7.0%} "
                   f"{p.hoard_score:>6.0%} {p.events_measured:>7}"
                   + (f"  DEAD: {dead}" if dead else ""))


@app.command("journal")
def journal(add: str = typer.Option(None, "--add"),
            kind: str = typer.Option("note", "--kind"),
            event: str = typer.Option(None, "--event"),
            season: int = SEASON_OPT, db: str = DB_OPT):
    """Week journal (F9): auto/manual log of rationale and results."""
    conn = _conn(db)
    season = _season(conn, season)
    if add:
        eid = store.resolve_event(conn, season, event)["event_id"] if event else None
        store.journal_add(conn, season, kind, add, eid)
        typer.echo("logged.")
        return
    df = store.journal_df(conn, season)
    typer.echo(df.to_string(index=False) if len(df) else "journal empty.")


@app.command("backtest")
def backtest_cmd(league_dir: str = typer.Option(..., "--league-dir"),
                 preds_dir: str = typer.Option(..., "--preds-dir"),
                 manager: str = typer.Option(None, "--manager"),
                 out: str = typer.Option(None, "--out",
                                         help="write golden JSON here"),
                 season: int = SEASON_OPT):
    """Replay a season per docs/BACKTEST_PLAN.md (engine vs actual, SumEV)."""
    season = int(season or _dt.date.today().year)
    df, summary = backtest_mod.replay(league_dir, preds_dir, season,
                                      manager, out)
    with pd.option_context("display.max_columns", None, "display.width", 200):
        typer.echo(df.to_string(index=False))
    typer.echo(f"\nSumEV engine {_money(summary['sum_ev_engine'])} vs actual "
               f"{_money(summary['sum_ev_actual'])} — "
               f"{'ACCEPT' if summary['accept_sum_ev'] else 'REGRESSION'}; "
               f"realized {_money(summary['sum_realized'])}")


if __name__ == "__main__":
    app()
