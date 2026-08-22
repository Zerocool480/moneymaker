"""Purse ladders, buckets, tie-splitting."""
import numpy as np

FRAC = np.array([.18,.109,.069,.049,.041,.03625,.03375,.03125,.02925,.02725,
 .02525,.02325,.02125,.01925,.01825,.01725,.01625,.01525,.01425,.01325,
 .01225,.01125,.01045,.00965,.00885,.00805,.00775,.00745,.00715,.00685,
 .00655,.00625,.00595,.0057,.00545,.0052,.00495,.0047,.0045,.0043,
 .0041,.0039,.0037,.0035,.0033,.0031,.0029,.0027,.0026,.0025])

def ladder(purse: float, n: int = 50) -> np.ndarray:
    f = FRAC[:n] if n <= len(FRAC) else np.concatenate(
        [FRAC, np.full(n - len(FRAC), FRAC[-1] * 0.9)])
    return f * purse

# Season-proven 2026 bucket ranges (ALGORITHMS s3). NOTE: buckets "35"/"610"/
# "41C" sit above the corresponding solo-position FRAC payouts — plausibly
# tie-group averaging (a T5 spanning positions 5-6 pays above solo-6th) and
# major-ladder steepness baked into the empirical ranges. Flagged in review;
# adjudicate against the 2026 archive per docs/BACKTEST_PLAN.md before
# changing — CLAUDE.md forbids "improving" proven math without a backtest.
BUCKETS = {"W": (.18,.18), "2": (.109,.109), "35": (.055,.085),
           "610": (.030,.048), "1120": (.016,.028), "2140": (.0075,.014),
           "41C": (.0035,.0065), "MC": (0,0)}
BUCKET_ORDER = ["W","2","35","610","1120","2140","41C","MC"]
