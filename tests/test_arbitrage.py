import pytest

from bot.services.arbitrage import analyze, japan_all_in_cost


def test_japan_all_in_cost(pricing):
    # 10000 JPY @ 0.006 €/JPY = 60 € base
    cost = japan_all_in_cost(10000, 0.006, pricing)
    base = 60.0
    proxy_comm = base * 0.05  # 3.0
    proxy_fixed = 3.0
    intl = 12.0
    pre_vat = base + proxy_comm + proxy_fixed + intl  # 78.0
    vat = pre_vat * 0.20
    assert cost.base_eur == pytest.approx(base)
    assert cost.proxy_commission == pytest.approx(proxy_comm)
    assert cost.import_vat == pytest.approx(vat)
    assert cost.total == pytest.approx(pre_vat + vat)


def test_analyze_detects_opportunity(pricing):
    # coût JP faible, revente élevée -> opportunité
    res = analyze(jpy_price=1000, fx_rate=0.006, resale_eur=80.0, config=pricing, min_margin=0.30)
    assert res.best is not None
    assert res.is_opportunity is True
    assert res.best.net_margin_pct >= 0.30


def test_analyze_no_opportunity_when_resale_too_low(pricing):
    res = analyze(jpy_price=10000, fx_rate=0.006, resale_eur=70.0, config=pricing, min_margin=0.30)
    # coût ~93 € > revente 70 € -> marge négative, pas d'opportunité
    assert res.is_opportunity is False
    assert res.best.net_margin_pct < 0.30


def test_analyze_threshold_from_config(pricing):
    res = analyze(jpy_price=1000, fx_rate=0.006, resale_eur=80.0, config=pricing)
    assert res.min_margin_threshold == pytest.approx(0.30)
