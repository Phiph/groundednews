from datetime import datetime, timedelta

import pytest

from bias import bias_breakdown, side_of, top_score

NOW = datetime(2026, 10, 11, 12, 0)


def outlets(*pairs):
    """[(name, bias_label), ...] -> the source dicts bias_breakdown takes."""
    return [{"source_name": name, "bias_label": label} for name, label in pairs]


def spread(left=0, center=0, right=0, unknown=0):
    """That many distinct outlets on each side."""
    return outlets(
        *[(f"L{i}", "left") for i in range(left)],
        *[(f"C{i}", "center") for i in range(center)],
        *[(f"R{i}", "right") for i in range(right)],
        *[(f"U{i}", "") for i in range(unknown)],
    )


@pytest.mark.parametrize("label, side", [
    ("left", "left"), ("center-left", "left"), ("center", "center"),
    ("center-right", "right"), ("right", "right"), ("", "unknown"), ("far-out", "unknown"),
])
def test_side_of_buckets_leaning_outlets_with_their_side(label, side):
    assert side_of(label) == side


def test_breakdown_counts_each_outlet_once():
    sources = outlets(("BBC", "center-left"), ("BBC", "center-left"), ("Fox", "right"), ("UPI", "center"))
    assert bias_breakdown(sources) == {"left": 1, "center": 1, "right": 1, "unknown": 0, "blindspot": None}


class TestBlindspot:
    def test_story_covered_only_by_the_left_is_a_blindspot_for_the_right(self):
        assert bias_breakdown(spread(left=3))["blindspot"] == "right"

    def test_story_covered_only_by_the_right_is_a_blindspot_for_the_left(self):
        assert bias_breakdown(spread(right=3))["blindspot"] == "left"

    def test_needs_at_least_three_outlets(self):
        assert bias_breakdown(spread(left=2))["blindspot"] is None

    def test_repeat_articles_from_one_outlet_dont_reach_the_minimum(self):
        sources = outlets(("Guardian", "left"), ("Guardian", "left"), ("NPR", "center-left"))
        assert bias_breakdown(sources)["blindspot"] is None

    def test_exactly_seventy_percent_is_enough(self):
        assert bias_breakdown(spread(left=7, center=3))["blindspot"] == "right"

    def test_below_seventy_percent_is_not(self):
        assert bias_breakdown(spread(left=2, center=1))["blindspot"] is None

    def test_unrated_outlets_count_toward_the_total(self):
        assert bias_breakdown(spread(left=2, unknown=1))["blindspot"] is None

    def test_any_coverage_from_the_other_side_rules_it_out(self):
        assert bias_breakdown(spread(left=9, right=1))["blindspot"] is None
        assert bias_breakdown(spread(right=9, left=1))["blindspot"] is None


def story(sources=1, articles=1, sides=("center",), hours_old=0.0, opinion=False):
    """A serialized cluster as far as top_score cares."""
    return {
        "source_count": sources,
        "article_count": articles,
        "bias": {side: (1 if side in sides else 0) for side in ("left", "center", "right")},
        "last_updated": NOW - timedelta(hours=hours_old),
        "is_opinion": opinion,
    }


class TestTopScore:
    def test_wider_coverage_ranks_higher(self):
        assert top_score(story(sources=5, articles=5), NOW) > top_score(story(sources=2, articles=2), NOW)

    def test_each_extra_side_adds_a_quarter(self):
        one = top_score(story(sources=3, sides=("left",)), NOW)
        assert top_score(story(sources=3, sides=("left", "right")), NOW) == pytest.approx(one * 1.25)
        assert top_score(story(sources=3, sides=("left", "center", "right")), NOW) == pytest.approx(one * 1.5)

    def test_opinion_only_stories_are_weighted_down(self):
        news = top_score(story(sources=4), NOW)
        assert top_score(story(sources=4, opinion=True), NOW) == pytest.approx(news * 0.25)

    def test_score_halves_after_eighteen_hours(self):
        fresh = top_score(story(sources=4), NOW)
        assert top_score(story(sources=4, hours_old=18), NOW) == pytest.approx(fresh / 2)
        assert top_score(story(sources=4, hours_old=36), NOW) == pytest.approx(fresh / 3)

    def test_stories_newer_than_the_reference_dont_get_a_boost(self):
        assert top_score(story(sources=4, hours_old=-5), NOW) == pytest.approx(top_score(story(sources=4), NOW))

    def test_coverage_formula(self):
        # 3 outlets, 4 articles, one side, fresh: 3**1.3 + 0.2 * 4
        assert top_score(story(sources=3, articles=4), NOW) == pytest.approx(3 ** 1.3 + 0.8)
