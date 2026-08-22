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
