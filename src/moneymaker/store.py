"""SQLite persistence layer. Schema: docs/DATA_MODEL.md (v1).

One addition over the v1 doc schema: golfers.is_amateur — the *current*
amateur flag derived from the latest predictions pull ("(a)" suffix).
turned_pro_date is set the first time a previously-amateur golfer appears
without the flag (the 2026 Koivun flip), after which they are pros forever.
"""
import datetime as _dt
import os
import re
import sqlite3

import pandas as pd

from . import league
from .datagolf import COLS, load_preds_csv
from .names import norm

SCHEMA = """
CREATE TABLE IF NOT EXISTS golfers(
  golfer_id INTEGER PRIMARY KEY,
  key TEXT UNIQUE NOT NULL,
  display_name TEXT,
  is_liv INTEGER DEFAULT 0,
  is_amateur INTEGER DEFAULT 0,
  turned_pro_date TEXT);
CREATE TABLE IF NOT EXISTS managers(
  manager_id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  is_self INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(
  event_id INTEGER PRIMARY KEY,
  season INTEGER NOT NULL,
  name TEXT NOT NULL,
  segment INTEGER,
  seq INTEGER,
  purse REAL,
  picks_per_manager INTEGER DEFAULT 1,
  has_cut INTEGER DEFAULT 1,
  field_type TEXT DEFAULT 'open',
  datagolf_event_id TEXT,
  UNIQUE(season, name, seq));
CREATE TABLE IF NOT EXISTS picks(
  season INTEGER NOT NULL,
  event_id INTEGER NOT NULL,
  manager_id INTEGER NOT NULL,
  slot INTEGER NOT NULL DEFAULT 0,
  golfer_id INTEGER,
  earnings REAL,
  PRIMARY KEY(season, event_id, manager_id, slot));
CREATE TABLE IF NOT EXISTS predictions(
  event_id INTEGER NOT NULL,
  golfer_id INTEGER NOT NULL,
  pulled_at TEXT NOT NULL,
  win REAL, top5 REAL, top10 REAL, top20 REAL, make_cut REAL,
  source TEXT,
  PRIMARY KEY(event_id, golfer_id, pulled_at));
CREATE TABLE IF NOT EXISTS field_entries(
  event_id INTEGER NOT NULL,
  golfer_id INTEGER NOT NULL,
  status TEXT DEFAULT 'committed',
  PRIMARY KEY(event_id, golfer_id));
CREATE TABLE IF NOT EXISTS standings_snapshots(
  season INTEGER NOT NULL,
  taken_at TEXT NOT NULL,
  manager_id INTEGER NOT NULL,
  board TEXT NOT NULL,
  total REAL,
  PRIMARY KEY(season, taken_at, manager_id, board));
CREATE TABLE IF NOT EXISTS journal(
  id INTEGER PRIMARY KEY,
  season INTEGER,
  event_id INTEGER,
  entry_at TEXT,
  kind TEXT,
  body TEXT);
"""

DEFAULT_DB = os.environ.get("MM_DB", "data/moneymaker.db")
_CLEAN_PAREN_RX = re.compile(r"\s*\(.*?\)")


def connect(path: str | None = None) -> sqlite3.Connection:
    path = path or DEFAULT_DB
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _display(raw: str) -> str:
    """Human display form: 'Last, First (WD)' -> 'First Last'."""
    s = _CLEAN_PAREN_RX.sub("", str(raw)).strip()
    if "," in s:
        last, first = [x.strip() for x in s.split(",", 1)]
        s = f"{first} {last}"
    return s


def golfer_id(conn, raw_name: str) -> int:
    key = norm(raw_name)
    row = conn.execute("SELECT golfer_id FROM golfers WHERE key=?", (key,)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO golfers(key, display_name) VALUES(?,?)",
                       (key, _display(raw_name)))
    return cur.lastrowid


def manager_id(conn, name: str) -> int:
    name = str(name).strip()
    row = conn.execute("SELECT manager_id FROM managers WHERE name=?", (name,)).fetchone()
    if row:
        return row[0]
    return conn.execute("INSERT INTO managers(name) VALUES(?)", (name,)).lastrowid


def set_self(conn, name: str):
    mid = manager_id(conn, name)
    conn.execute("UPDATE managers SET is_self=0")
    conn.execute("UPDATE managers SET is_self=1 WHERE manager_id=?", (mid,))
    conn.commit()


def self_manager(conn) -> str | None:
    row = conn.execute("SELECT name FROM managers WHERE is_self=1").fetchone()
    return row[0] if row else None


def set_liv(conn, names: list[str], value: bool = True):
    for n in names:
        gid = golfer_id(conn, n)
        conn.execute("UPDATE golfers SET is_liv=? WHERE golfer_id=?",
                     (int(value), gid))
    conn.commit()


def liv_keys(conn) -> set:
    return {r[0] for r in conn.execute("SELECT key FROM golfers WHERE is_liv=1")}


def amateur_keys(conn) -> set:
    return {r[0] for r in conn.execute(
        "SELECT key FROM golfers WHERE is_amateur=1 AND turned_pro_date IS NULL")}


# ---------------------------------------------------------------- ingestion

def ingest_league(conn, xlsx_path, season: int, self_name: str | None = None) -> dict:
    """Load a league workbook snapshot: events, managers, picks (with Money
    Earned settlement), standings snapshot. The sheet is the source of truth —
    the season's picks are replaced wholesale."""
    sel, _ = league.load_selections(xlsx_path)
    groups = league.group_events(league.event_columns(sel))

    event_ids = {}
    for g in groups:
        row = conn.execute(
            "SELECT event_id FROM events WHERE season=? AND name=? AND seq=?",
            (season, g["title"], g["seq"])).fetchone()
        if row:
            eid = row[0]
            conn.execute(
                "UPDATE events SET segment=?, purse=COALESCE(?, purse), "
                "picks_per_manager=? WHERE event_id=?",
                (g["segment"], g["purse"], len(g["cols"]), eid))
        else:
            eid = conn.execute(
                "INSERT INTO events(season, name, segment, seq, purse, "
                "picks_per_manager, field_type) VALUES(?,?,?,?,?,?,?)",
                (season, g["title"], g["segment"], g["seq"], g["purse"],
                 len(g["cols"]),
                 "major" if len(g["cols"]) == 2 else "open")).lastrowid
        event_ids[g["seq"]] = eid

    conn.execute("DELETE FROM picks WHERE season=?", (season,))
    n_picks = 0
    for g in groups:
        eid = event_ids[g["seq"]]
        for mname, entries in league.group_picks(sel, g).items():
            mid = manager_id(conn, mname)
            for slot, raw in entries:
                conn.execute(
                    "INSERT OR REPLACE INTO picks(season, event_id, manager_id,"
                    " slot, golfer_id) VALUES(?,?,?,?,?)",
                    (season, eid, mid, slot, golfer_id(conn, raw)))
                n_picks += 1

    me, me_groups = league.load_money_earned(xlsx_path)
    n_settled = 0
    if me is not None:
        by_title = {}
        for g in me_groups:
            by_title.setdefault(g["title"], []).append(g)
        seen = {}
        for g in groups:
            idx = seen.get(g["title"], 0)
            seen[g["title"]] = idx + 1
            cands = by_title.get(g["title"], [])
            if idx >= len(cands):
                continue
            meg = cands[idx]
            eid = event_ids[g["seq"]]
            for mname, vals in league.group_earnings(me, meg).items():
                mid = manager_id(conn, mname)
                for slot, dollars in vals.items():
                    cur = conn.execute(
                        "UPDATE picks SET earnings=? WHERE season=? AND "
                        "event_id=? AND manager_id=? AND slot=?",
                        (dollars, season, eid, mid, slot))
                    n_settled += cur.rowcount

    taken = _now()
    n_rows = 0
    for board in ("overall", "segment1", "segment2", "segment3", "segment4"):
        try:
            rows = league.standings(xlsx_path, board)
        except Exception:
            continue
        for name, total in rows:
            mid = manager_id(conn, name)
            conn.execute(
                "INSERT OR REPLACE INTO standings_snapshots(season, taken_at,"
                " manager_id, board, total) VALUES(?,?,?,?,?)",
                (season, taken, mid, board, total))
            n_rows += 1

    if self_name:
        set_self(conn, self_name)
    conn.commit()
    return {"events": len(groups), "picks": n_picks, "settled": n_settled,
            "standings_rows": n_rows}


def ingest_preds_frame(conn, d: pd.DataFrame, event_id: int,
                       source: str = "csv") -> dict:
    """Store one predictions pull + field entries; refresh amateur flags and
    the event's has_cut auto-detection."""
    pulled = _now()
    today = pulled[:10]
    conn.execute("DELETE FROM field_entries WHERE event_id=?", (event_id,))
    for _, r in d.iterrows():
        gid = golfer_id(conn, r["player_name"])
        amateur = bool(r.get("amateur", False))
        g = conn.execute("SELECT is_amateur, turned_pro_date FROM golfers "
                         "WHERE golfer_id=?", (gid,)).fetchone()
        if amateur and g["turned_pro_date"] is None:
            conn.execute("UPDATE golfers SET is_amateur=1 WHERE golfer_id=?", (gid,))
        elif not amateur and g["is_amateur"]:
            conn.execute("UPDATE golfers SET is_amateur=0, turned_pro_date=? "
                         "WHERE golfer_id=?", (today, gid))
        conn.execute(
            "INSERT OR REPLACE INTO predictions(event_id, golfer_id, pulled_at,"
            " win, top5, top10, top20, make_cut, source) VALUES(?,?,?,?,?,?,?,?,?)",
            (event_id, gid, pulled, float(r["win"]), float(r["top_5"]),
             float(r["top_10"]), float(r["top_20"]), float(r["make_cut"]), source))
        conn.execute(
            "INSERT OR REPLACE INTO field_entries(event_id, golfer_id, status)"
            " VALUES(?,?, 'committed')", (event_id, gid))
    has_cut = bool(d.attrs.get("has_cut", True))
    conn.execute("UPDATE events SET has_cut=? WHERE event_id=?",
                 (int(has_cut), event_id))
    conn.commit()
    return {"rows": len(d), "has_cut": has_cut, "pulled_at": pulled}


def ingest_preds_csv(conn, csv_path, event_id: int) -> dict:
    return ingest_preds_frame(conn, load_preds_csv(csv_path), event_id, "csv")


# ------------------------------------------------------------------ queries

def resolve_event(conn, season: int, fragment: str):
    """Find one event by (case/punct-insensitive) substring of its name."""
    frag = norm(fragment)
    rows = conn.execute(
        "SELECT * FROM events WHERE season=? ORDER BY seq", (season,)).fetchall()
    hits = [r for r in rows if frag in norm(r["name"])]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        names = ", ".join(r["name"] for r in rows) or "(no events ingested)"
        raise KeyError(f"no event matching {fragment!r}; have: {names}")
    raise KeyError(f"ambiguous event {fragment!r}: "
                   + ", ".join(r["name"] for r in hits))


def events_df(conn, season: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT * FROM events WHERE season=? ORDER BY seq", conn, params=(season,))


def used_set(conn, season: int, manager: str) -> set:
    rows = conn.execute(
        "SELECT g.key FROM picks p JOIN golfers g ON g.golfer_id=p.golfer_id "
        "JOIN managers m ON m.manager_id=p.manager_id "
        "WHERE p.season=? AND m.name=?", (season, manager)).fetchall()
    return {r[0] for r in rows}


def latest_preds(conn, event_id: int) -> pd.DataFrame:
    """Most recent pull for an event, in the DataGolf CSV contract shape
    (key, win, top_5, top_10, top_20, make_cut, amateur, display_name)."""
    row = conn.execute("SELECT MAX(pulled_at) FROM predictions WHERE event_id=?",
                       (event_id,)).fetchone()
    if not row or row[0] is None:
        raise KeyError(f"no predictions ingested for event_id={event_id}")
    d = pd.read_sql_query(
        "SELECT g.key, g.display_name, g.is_liv,"
        " (g.is_amateur AND g.turned_pro_date IS NULL) AS amateur,"
        " p.win, p.top5 AS top_5, p.top10 AS top_10, p.top20 AS top_20,"
        " p.make_cut FROM predictions p JOIN golfers g ON g.golfer_id=p.golfer_id"
        " WHERE p.event_id=? AND p.pulled_at=?", conn, params=(event_id, row[0]))
    d["amateur"] = d["amateur"].astype(bool)
    d["is_liv"] = d["is_liv"].astype(bool)
    d.attrs["pulled_at"] = row[0]
    return d


def events_with_preds(conn, season: int) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT e.event_id FROM events e JOIN predictions p "
        "ON p.event_id=e.event_id WHERE e.season=? ORDER BY e.seq",
        (season,)).fetchall()
    return [r[0] for r in rows]


def latest_standings(conn, season: int, board: str = "overall") -> dict:
    row = conn.execute(
        "SELECT MAX(taken_at) FROM standings_snapshots WHERE season=? AND board=?",
        (season, board)).fetchone()
    if not row or row[0] is None:
        return {}
    rows = conn.execute(
        "SELECT m.name, s.total FROM standings_snapshots s "
        "JOIN managers m ON m.manager_id=s.manager_id "
        "WHERE s.season=? AND s.board=? AND s.taken_at=? ORDER BY s.total DESC",
        (season, board, row[0])).fetchall()
    return {r[0]: r[1] for r in rows}


def picks_df(conn, season: int) -> pd.DataFrame:
    """All picks with manager/golfer/event names + earnings (long form)."""
    return pd.read_sql_query(
        "SELECT p.season, p.event_id, e.name AS event, e.seq, e.segment,"
        " m.name AS manager, m.is_self, p.slot, g.key, g.display_name,"
        " p.earnings FROM picks p"
        " JOIN events e ON e.event_id=p.event_id"
        " JOIN managers m ON m.manager_id=p.manager_id"
        " JOIN golfers g ON g.golfer_id=p.golfer_id"
        " WHERE p.season=? ORDER BY e.seq, m.name, p.slot",
        conn, params=(season,))


def event_picks(conn, season: int, event_id: int) -> dict:
    """manager -> [golfer keys] for one event."""
    out = {}
    for r in conn.execute(
            "SELECT m.name, g.key FROM picks p"
            " JOIN managers m ON m.manager_id=p.manager_id"
            " JOIN golfers g ON g.golfer_id=p.golfer_id"
            " WHERE p.season=? AND p.event_id=? ORDER BY p.slot",
            (season, event_id)):
        out.setdefault(r[0], []).append(r[1])
    return out


def managers_list(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT name FROM managers ORDER BY name")]


def ineligible_keys(conn, event_row, preds: pd.DataFrame) -> dict:
    """key -> reason, for golfers barred at this event (LIV outside majors).
    Amateurs are NOT ineligible — they're $0-EV flagged (visible, loud)."""
    out = {}
    if event_row["field_type"] != "major":
        for k in set(preds["key"]) & liv_keys(conn):
            out[k] = "LIV: majors only"
    return out


def journal_add(conn, season: int, kind: str, body: str,
                event_id: int | None = None):
    conn.execute(
        "INSERT INTO journal(season, event_id, entry_at, kind, body)"
        " VALUES(?,?,?,?,?)", (season, event_id, _now(), kind, body))
    conn.commit()


def journal_df(conn, season: int) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT j.entry_at, j.kind, e.name AS event, j.body FROM journal j"
        " LEFT JOIN events e ON e.event_id=j.event_id WHERE j.season=?"
        " ORDER BY j.entry_at", conn, params=(season,))
