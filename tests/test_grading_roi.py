import pytest

from bot.services.grading_roi import estimate, grading_cost


def test_grading_cost_from_config(pricing):
    # psa: 25 + 20 + 5 = 50
    assert grading_cost("psa", pricing) == pytest.approx(50.0)


def test_estimate_break_even_grade(pricing):
    raw = 20.0
    graded = {"PSA 9": 60.0, "PSA 10": 150.0, "PSA 8": 30.0}
    roi = estimate("psa", raw, graded, pricing)
    # coût = 50, invest = 70
    # PSA 8: 30 - 20 - 50 = -40 (négatif)
    # PSA 9: 60 - 70 = -10 (négatif)
    # PSA 10: 150 - 70 = +80 (positif)
    by_grade = {o.grade: o for o in roi.outcomes}
    assert by_grade["PSA 8"].net_gain == pytest.approx(-40.0)
    assert by_grade["PSA 10"].net_gain == pytest.approx(80.0)
    # point mort = première note (croissante) avec gain >= 0 -> PSA 10
    assert roi.break_even_grade == "PSA 10"


def test_estimate_sorted_grades(pricing):
    roi = estimate("cgc", 10.0, {"CGC 10": 100, "CGC 9": 40, "CGC 9.5": 70}, pricing)
    grades = [o.grade for o in roi.outcomes]
    assert grades == ["CGC 9", "CGC 9.5", "CGC 10"]
