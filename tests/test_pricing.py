import pytest

from bot.services.pricing import (
    CostBreakdown,
    break_even,
    cheapest_break_even,
    compute_all,
    compute_platform,
    net_profit,
    parse_calc_message,
)


def test_break_even_formula():
    # cost 10, rate_sum 0.184, fixed 0 -> 10 / 0.816
    assert break_even(10.0, 0.184, 0.0) == pytest.approx(10.0 / 0.816)


def test_break_even_with_fixed_fee():
    assert break_even(10.0, 0.244, 0.35) == pytest.approx(10.35 / 0.756)


def test_break_even_impossible_when_rates_exceed_100pct():
    with pytest.raises(ValueError):
        break_even(10.0, 1.0, 0.0)


def test_net_profit_zero_at_break_even():
    p_min = break_even(10.0, 0.184, 0.0)
    assert net_profit(p_min, 10.0, 0.184, 0.0) == pytest.approx(0.0, abs=1e-9)


def test_cost_breakdown_total():
    c = CostBreakdown(purchase=10, import_fees=2, shipping_in=3, shipping_out=1)
    assert c.total == 16


def test_compute_platform_tiers(pricing):
    cm = pricing.platforms["cardmarket"]
    res = compute_platform("cardmarket", cm, pricing.charges, cost_total=10.0)
    # premier tier = point mort, profit ~0
    assert res.tiers[0].pct_above == 0.0
    assert res.tiers[0].net_profit == pytest.approx(0.0, abs=1e-9)
    # +30 % donne un profit strictement positif et une marge cohérente
    last = res.tiers[-1]
    assert last.pct_above == 0.30
    assert last.net_profit > 0
    assert 0 < last.net_margin_pct < 1


def test_compute_all_and_cheapest(pricing):
    cost = CostBreakdown(purchase=10.0)
    results = compute_all(cost, pricing)
    keys = {r.platform for r in results}
    assert keys == {"cardmarket", "ebay", "tiktok"}
    cheapest = cheapest_break_even(results)
    # Cardmarket (commission 5 %) doit être la moins-disante
    assert cheapest.platform == "cardmarket"


def test_compute_all_filter_platform(pricing):
    cost = CostBreakdown(purchase=10.0)
    results = compute_all(cost, pricing, platforms=["ebay"])
    assert len(results) == 1 and results[0].platform == "ebay"


@pytest.mark.parametrize(
    "text,value,currency,platform",
    [
        ("12000 jpy ebay", 12000.0, "jpy", "ebay"),
        ("35€ cm", 35.0, "eur", "cardmarket"),
        ("5000¥", 5000.0, "jpy", None),
        ("12,50 eur tiktok", 12.5, "eur", "tiktok"),
        ("1.234,56 € cardmarket", 1234.56, "eur", "cardmarket"),
        ("8000 yen tts", 8000.0, "jpy", "tiktok"),
    ],
)
def test_parse_calc_message(text, value, currency, platform):
    parsed = parse_calc_message(text)
    assert parsed is not None
    assert parsed.value == pytest.approx(value)
    assert parsed.currency == currency
    assert parsed.platform == platform


def test_parse_calc_message_empty():
    assert parse_calc_message("aucun chiffre ici") is None
