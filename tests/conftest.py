"""Synthetic mini-season fixtures matching the DATA_MODEL sheet contract.

4 events: Sony (seg1), Farmers (seg1), PGA Championship (MAJOR, two adjacent
columns, seg2), Travelers (no-cut, seg2). Hazards baked in: accents
(Åberg/Højgaard), a "(WD)" pick that still consumes the golfer, an amateur
"(a)" in the preds, and a LIV member (Rahm) legal at the major only.
"""
import openpyxl
import pandas as pd
import pytest

HDR = ["Manager", "Sony Open- $8.3M", "Farmers Insurance- $9.3M", "Segment 2",
       "PGA Championship- $19M", "PGA Championship- $19M", "Travelers- $20M",
       "Weak Open- $6M"]
SONY, FARMERS, PGA1, PGA2, TRAV, WEAK = 1, 2, 4, 5, 6, 7
MANAGERS = ["Jay Doura", "Mirror Max", "Rival One", "Rival Two", "Chalk Charlie"]

SEL_SETTLED = {
    "Jay Doura":     {SONY: "Spaun, J.J.", FARMERS: "Morikawa, Collin (WD)"},
    "Mirror Max":    {SONY: "Spaun, J.J.", FARMERS: "Morikawa, Collin"},
    "Rival One":     {SONY: "English, Harris", FARMERS: "Hovland, Viktor"},
    "Rival Two":     {SONY: "Gotterup, Chris", FARMERS: "Fox, Ryan"},
    "Chalk Charlie": {SONY: "Thomas, Justin", FARMERS: "Åberg, Ludvig"},
}
MONEY_SETTLED = {
    "Jay Doura":     {SONY: 40_000, FARMERS: 0},
    "Mirror Max":    {SONY: 40_000, FARMERS: 0},
    "Rival One":     {SONY: 120_000, FARMERS: 500_000},
    "Rival Two":     {SONY: 1_584_000, FARMERS: 80_000},
    "Chalk Charlie": {SONY: 200_000, FARMERS: 300_000},
}
SEL_PGA = {
    "Jay Doura":     {PGA1: "Hovland, Viktor", PGA2: "Thomas, Justin"},
    "Mirror Max":    {PGA1: "Scheffler, Scottie", PGA2: "Åberg, Ludvig"},
    "Rival One":     {PGA1: "McIlroy, Rory", PGA2: "Rahm, Jon"},
    "Rival Two":     {PGA1: "Højgaard, Rasmus", PGA2: "Spaun, J.J."},
    "Chalk Charlie": {PGA1: "Koivun, Jackson", PGA2: "English, Harris"},
}
MONEY_PGA = {
    "Jay Doura":     {PGA1: 500_000, PGA2: 150_000},
    "Mirror Max":    {PGA1: 1_000_000, PGA2: 90_000},
    "Rival One":     {PGA1: 300_000, PGA2: 800_000},
    "Rival Two":     {PGA1: 60_000, PGA2: 45_000},
    "Chalk Charlie": {PGA1: 0, PGA2: 70_000},
}


def _totals(*money_dicts):
    out = {m: 0.0 for m in MANAGERS}
    for md in money_dicts:
        for m, cells in md.items():
            out[m] += sum(cells.values())
    return sorted(out.items(), key=lambda kv: -kv[1])


def write_workbook(path, sel, money, standings):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Selections"
    ws.append(HDR)
    for m in MANAGERS:
        row = [m] + [None] * (len(HDR) - 1)
        for c, v in sel.get(m, {}).items():
            row[c] = v
        ws.append(row)
    me = wb.create_sheet("Money Earned")
    me.append(HDR)
    for m in MANAGERS:
        row = [m] + [None] * (len(HDR) - 1)
        for c, v in money.get(m, {}).items():
            row[c] = v
        me.append(row)
    st = wb.create_sheet("Standings")
    st.append([None] * 14)
    seg1 = standings.get("segment1", [])
    seg2 = standings.get("segment2", [])
    for i, (name, tot) in enumerate(standings["overall"]):
        r = [None] * 14
        r[1], r[2] = name, tot
        if i < len(seg1):
            r[6], r[7] = seg1[i]
        if i < len(seg2):
            r[8], r[9] = seg2[i]
        st.append(r)
    wb.save(path)
    return path


def _merge(*dicts):
    out = {m: {} for m in MANAGERS}
    for d in dicts:
        for m, cells in d.items():
            out[m].update(cells)
    return out


@pytest.fixture(scope="session")
def wb_mid(tmp_path_factory):
    """Mid-season: Sony+Farmers settled, PGA locked for Rival One only."""
    sel = _merge(SEL_SETTLED,
                 {"Rival One": {PGA1: "McIlroy, Rory", PGA2: "Rahm, Jon"}})
    st = {"overall": _totals(MONEY_SETTLED),
          "segment1": _totals(MONEY_SETTLED),
          "segment2": [(m, 0) for m in MANAGERS]}
    return write_workbook(tmp_path_factory.mktemp("wb") / "mid.xlsx",
                          sel, MONEY_SETTLED, st)


@pytest.fixture(scope="session")
def wb_early(tmp_path_factory):
    """After Sony only (backtest deadline snapshot for everything later)."""
    sel = {m: {SONY: v[SONY]} for m, v in SEL_SETTLED.items()}
    money = {m: {SONY: v[SONY]} for m, v in MONEY_SETTLED.items()}
    st = {"overall": _totals(money), "segment1": _totals(money)}
    return write_workbook(tmp_path_factory.mktemp("wb") / "a_early.xlsx",
                          sel, money, st)


@pytest.fixture(scope="session")
def wb_sunday(tmp_path_factory):
    """PGA locked for everyone, money not yet settled (Saturday night)."""
    sel = _merge(SEL_SETTLED, SEL_PGA)
    st = {"overall": _totals(MONEY_SETTLED),
          "segment1": _totals(MONEY_SETTLED)}
    return write_workbook(tmp_path_factory.mktemp("wb") / "sunday.xlsx",
                          sel, MONEY_SETTLED, st)


@pytest.fixture(scope="session")
def wb_final(tmp_path_factory):
    """PGA played and settled."""
    sel = _merge(SEL_SETTLED, SEL_PGA)
    money = _merge(MONEY_SETTLED, MONEY_PGA)
    st = {"overall": _totals(MONEY_SETTLED, MONEY_PGA),
          "segment1": _totals(MONEY_SETTLED),
          "segment2": _totals(MONEY_PGA)}
    return write_workbook(tmp_path_factory.mktemp("wb") / "z_final.xlsx",
                          sel, money, st)


PGA_PREDS = [
    # player_name, win, top_5, top_10, top_20, make_cut
    ("Scheffler, Scottie", .16, .35, .48, .65, .92),
    ("McIlroy, Rory",      .12, .30, .42, .60, .90),
    ("Rahm, Jon",          .10, .27, .38, .56, .90),
    ("Hovland, Viktor",    .05, .18, .28, .45, .85),
    ("Åberg, Ludvig",      .05, .17, .27, .44, .85),
    ("Thomas, Justin",     .04, .15, .24, .40, .82),
    ("Koivun, Jackson (a)", .03, .12, .20, .35, .80),
    ("Højgaard, Rasmus",   .02, .09, .16, .30, .75),
    ("English, Harris",    .015, .07, .13, .25, .70),
    ("Gotterup, Chris",    .012, .06, .11, .22, .68),
    ("Spaun, J.J.",        .01, .05, .10, .20, .65),
    ("Fox, Ryan",          .008, .04, .08, .17, .60),
]
TRAV_PREDS = [
    ("Scheffler, Scottie", .18, .38, .52, .70, 1.0),
    ("Rahm, Jon",          .12, .30, .42, .60, 1.0),
    ("Hovland, Viktor",    .06, .20, .30, .48, 1.0),
    ("Åberg, Ludvig",      .06, .19, .29, .47, 1.0),
    ("Thomas, Justin",     .05, .17, .26, .43, 1.0),
    ("Koivun, Jackson",    .04, .14, .22, .38, 1.0),  # turned pro (the flip)
    ("English, Harris",    .02, .09, .16, .30, 1.0),
    ("Gotterup, Chris",    .018, .08, .14, .27, 1.0),
    ("Fox, Ryan",          .01, .05, .10, .20, 1.0),
    ("Bradley, Keegan",    .03, .12, .20, .35, 1.0),
]
WEAK_PREDS = [
    ("Scheffler, Scottie", .20, .40, .55, .72, .90),
    ("Hovland, Viktor",    .07, .22, .33, .50, .85),
    ("Thomas, Justin",     .06, .20, .30, .46, .84),
    ("Bradley, Keegan",    .05, .17, .26, .40, .80),
    ("English, Harris",    .03, .11, .19, .33, .75),
    ("Gotterup, Chris",    .025, .10, .17, .30, .72),
    ("Fox, Ryan",          .015, .07, .13, .24, .65),
]


def _preds_csv(path, rows):
    pd.DataFrame(rows, columns=["player_name", "win", "top_5", "top_10",
                                "top_20", "make_cut"]).assign(
        sample_size=1000).to_csv(path, index=False)
    return path


@pytest.fixture(scope="session")
def pga_csv(tmp_path_factory):
    return _preds_csv(tmp_path_factory.mktemp("dg") / "pga.csv", PGA_PREDS)


@pytest.fixture(scope="session")
def travelers_csv(tmp_path_factory):
    return _preds_csv(tmp_path_factory.mktemp("dg") / "travelers.csv",
                      TRAV_PREDS)


@pytest.fixture(scope="session")
def weak_csv(tmp_path_factory):
    return _preds_csv(tmp_path_factory.mktemp("dg") / "weak_open.csv",
                      WEAK_PREDS)


@pytest.fixture(scope="session")
def positions_csv(tmp_path_factory):
    rows = [("Scheffler, Scottie", -12), ("McIlroy, Rory", -10),
            ("Hovland, Viktor", -11), ("Rahm, Jon", -9),
            ("Thomas, Justin", -8), ("Åberg, Ludvig", -7),
            ("Højgaard, Rasmus", -6), ("English, Harris", -5),
            ("Koivun, Jackson", -4)]
    p = tmp_path_factory.mktemp("live") / "positions.csv"
    pd.DataFrame(rows, columns=["player_name", "to_par"]).to_csv(p, index=False)
    return p


SEASON = 2027


@pytest.fixture()
def db_mid(wb_mid, pga_csv, travelers_csv):
    """In-memory store with the mid-season workbook + both preds ingested."""
    from moneymaker import store
    conn = store.connect(":memory:")
    store.ingest_league(conn, wb_mid, SEASON, self_name="Jay Doura")
    store.set_liv(conn, ["Rahm, Jon"])
    pga = store.resolve_event(conn, SEASON, "pga championship")
    trav = store.resolve_event(conn, SEASON, "travelers")
    store.ingest_preds_csv(conn, pga_csv, pga["event_id"])
    store.ingest_preds_csv(conn, travelers_csv, trav["event_id"])
    return conn


@pytest.fixture()
def db_final(wb_final):
    """Season over: every major settled (dead-hoard scenarios)."""
    from moneymaker import store
    conn = store.connect(":memory:")
    store.ingest_league(conn, wb_final, SEASON, self_name="Jay Doura")
    store.set_liv(conn, ["Rahm, Jon", "Bradley, Keegan"])
    return conn
