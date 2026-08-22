"""League workbook parser + rules. Contract: docs/DATA_MODEL.md."""
import re
import pandas as pd
from .names import norm

SEGMENT_RX = re.compile(r"^\s*Segment\s*\d", re.I)
PURSE_RX = re.compile(r"\$([\d.]+)\s*M", re.I)

def load_selections(path):
    sel = pd.read_excel(path, sheet_name="Selections", header=None)
    hdr = sel.iloc[0].tolist()
    events = []  # (col, title, purse_or_None); majors appear twice
    for c in range(1, len(hdr)):
        h = hdr[c]
        if pd.isna(h) or SEGMENT_RX.match(str(h)):
            continue
        m = PURSE_RX.search(str(h))
        events.append((c, str(h).strip(), float(m.group(1))*1e6 if m else None))
    return sel, events

def used_set(sel, manager: str) -> set:
    rows = [i for i in range(1, len(sel)) if str(sel.iloc[i, 0]).strip() == manager]
    if not rows:
        raise KeyError(f"manager not found: {manager}")
    r = rows[0]
    hdr = sel.iloc[0].tolist()
    out = set()
    for c in range(1, sel.shape[1]):
        h = hdr[c]
        if pd.isna(h) or SEGMENT_RX.match(str(h)):
            continue
        v = sel.iloc[r, c]
        if pd.notna(v):
            out.add(norm(v))
    return out

def standings(path, board="overall"):
    st = pd.read_excel(path, sheet_name="Standings", header=None)
    cols = {"overall": (1, 2), "segment1": (6, 7), "segment2": (8, 9),
            "segment3": (10, 11), "segment4": (12, 13)}[board]
    out = []
    for i in range(1, len(st)):
        n, v = st.iloc[i, cols[0]], st.iloc[i, cols[1]]
        if pd.notna(n) and pd.notna(v):
            out.append((str(n).strip(), float(v)))
    return out

def event_picks(sel, col: int) -> dict:
    """manager -> normalized pick key at one event column (None if empty)."""
    out = {}
    for i in range(1, len(sel)):
        n = sel.iloc[i, 0]
        if pd.isna(n):
            continue
        v = sel.iloc[i, col]
        out[str(n).strip()] = norm(v) if pd.notna(v) else None
    return out


SEGMENT_NUM_RX = re.compile(r"Segment\s*(\d+)", re.I)


def event_columns(sel):
    """Header row -> [(col, title, purse_or_None, segment)]. Segment marker
    columns ("Segment N") set the segment for the events that FOLLOW them;
    events before any marker are segment 1."""
    hdr = sel.iloc[0].tolist()
    seg = 1
    out = []
    for c in range(1, len(hdr)):
        h = hdr[c]
        if pd.isna(h):
            continue
        m = SEGMENT_NUM_RX.search(str(h))
        if SEGMENT_RX.match(str(h)):
            if m:
                seg = int(m.group(1))
            continue
        pm = PURSE_RX.search(str(h))
        out.append((c, str(h).strip(), float(pm.group(1)) * 1e6 if pm else None, seg))
    return out


def group_events(cols):
    """Group ADJACENT same-title columns (majors span two columns).
    Returns [{title, purse, segment, cols: [c] or [c1, c2], seq}]."""
    groups = []
    for c, title, purse, seg in cols:
        if groups and groups[-1]["title"] == title and \
                groups[-1]["cols"][-1] in (c - 1, c - 2):
            groups[-1]["cols"].append(c)
        else:
            groups.append({"title": title, "purse": purse, "segment": seg,
                           "cols": [c]})
    for i, g in enumerate(groups):
        g["seq"] = i
    return groups


def manager_rows(sel) -> dict:
    """manager name -> sheet row index (first occurrence)."""
    out = {}
    for i in range(1, len(sel)):
        n = sel.iloc[i, 0]
        if pd.notna(n) and str(n).strip() and str(n).strip() not in out:
            out[str(n).strip()] = i
    return out


def group_picks(sel, group) -> dict:
    """manager -> [(slot, raw_cell_str)] for one grouped event (majors: 2 slots).
    Empty cells are omitted; '(WD)'-annotated cells still count as picks."""
    out = {}
    for name, r in manager_rows(sel).items():
        entries = []
        for slot, c in enumerate(group["cols"]):
            v = sel.iloc[r, c]
            if pd.notna(v) and str(v).strip():
                entries.append((slot, str(v).strip()))
        out[name] = entries
    return out


def load_money_earned(path):
    """'Money Earned' tab mirrors the Selections layout; cells are dollar
    amounts. Returns (df, grouped_events) or (None, None) if the tab is absent."""
    try:
        me = pd.read_excel(path, sheet_name="Money Earned", header=None)
    except ValueError:
        return None, None
    return me, group_events(event_columns(me))


def group_earnings(me, group) -> dict:
    """manager -> {slot: dollars} for one grouped Money Earned event column."""
    out = {}
    for name, r in manager_rows(me).items():
        vals = {}
        for slot, c in enumerate(group["cols"]):
            v = pd.to_numeric(me.iloc[r, c], errors="coerce")
            if pd.notna(v):
                vals[slot] = float(v)
        out[name] = vals
    return out
