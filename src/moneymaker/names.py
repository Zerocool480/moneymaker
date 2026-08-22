"""Name normalization -- the backbone of every join. Season-proven."""
import re
_FOLD = str.maketrans({"\u00f8":"o","\u00e9":"e","\u00e5":"a","\u00e4":"a",
                       "\u00f6":"o","\u00ed":"i","\u00fa":"u"})

def norm(s) -> str:
    """'Hojgaard, Rasmus' -> 'rasmus hojgaard'; strips (WD)/(a) etc."""
    s = str(s)
    if "," in s:
        last, first = [x.strip() for x in s.split(",", 1)]
        s = f"{first} {last}"
    s = s.lower().translate(_FOLD)
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"[^a-z ]", "", s)
    return " ".join(s.split())


_PURSE_SUFFIX = re.compile(r"[-–]?\s*\$[\d.]+\s*M\s*$", re.I)


def norm_event(s) -> str:
    """Event-title key: KEEPS digits (person-norm would turn '3M Open' into
    'm open' and match everything). Strips the '- $10M' purse suffix so a
    purse announcement doesn't change an event's identity."""
    s = _PURSE_SUFFIX.sub("", str(s))
    s = s.lower().translate(_FOLD)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())
