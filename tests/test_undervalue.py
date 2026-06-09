import pytest

from bot.services.undervalue import below_market_pct, evaluate, looks_like_scam


def test_below_market_pct():
    assert below_market_pct(75, 100) == pytest.approx(0.25)
    assert below_market_pct(100, 0) == 0.0


def test_evaluate_is_deal():
    res = evaluate(70, 100, 0.20)
    assert res.is_deal is True
    assert res.discount_pct == pytest.approx(0.30)


def test_evaluate_not_a_deal():
    res = evaluate(95, 100, 0.20)
    assert res.is_deal is False


def test_looks_like_scam():
    assert looks_like_scam(30, 100) is True   # 70 % sous le marché
    assert looks_like_scam(70, 100) is False  # 30 % sous le marché
