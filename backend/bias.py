"""Coverage-bias rules shared by the API, the agent scripts and the tests."""
from datetime import datetime

# Ground News-style buckets: leaning outlets count toward their side
BIAS_BUCKETS = {"left": "left", "center-left": "left", "center": "center",
                "center-right": "right", "right": "right"}
SIDES = ("left", "center", "right")
BLINDSPOT_MIN_SOURCES = 3
BLINDSPOT_SHARE = 0.7

SPECTRUM_BONUS = 0.25       # per extra side (left/center/right) covering the story
OPINION_ONLY_WEIGHT = 0.25  # stories with no straight reporting yet sink below news


def side_of(bias_label: str) -> str:
    """"left" | "center" | "right", or "unknown" for unrated outlets."""
    return BIAS_BUCKETS.get(bias_label, "unknown")


def bias_breakdown(sources: list[dict]) -> dict:
    """Distinct-outlet counts per side, plus which side (if any) is ignoring the story.
    Each source dict needs `source_name` and `bias_label`."""
    outlets: dict[str, str] = {}
    for s in sources:
        outlets[s["source_name"]] = side_of(s["bias_label"])
    counts = {"left": 0, "center": 0, "right": 0, "unknown": 0}
    for side in outlets.values():
        counts[side] += 1
    total = len(outlets)
    blindspot = None
    if total >= BLINDSPOT_MIN_SOURCES:
        # "Blindspot for the right" = covered almost entirely by the left, and vice versa
        if counts["right"] == 0 and counts["left"] / total >= BLINDSPOT_SHARE:
            blindspot = "right"
        elif counts["left"] == 0 and counts["right"] / total >= BLINDSPOT_SHARE:
            blindspot = "left"
    return {**counts, "blindspot": blindspot}


def top_score(story: dict, newest: datetime) -> float:
    """Wider coverage ranks higher, especially coverage from across the spectrum;
    older stories decay over roughly a day. `story` is a serialized cluster."""
    hours_old = max((newest - story["last_updated"]).total_seconds() / 3600, 0)
    coverage = story["source_count"] ** 1.3 + 0.2 * story["article_count"]
    sides = sum(1 for side in SIDES if story["bias"][side])
    score = coverage * (1 + SPECTRUM_BONUS * max(sides - 1, 0)) / (1 + hours_old / 18)
    return score * OPINION_ONLY_WEIGHT if story["is_opinion"] else score
