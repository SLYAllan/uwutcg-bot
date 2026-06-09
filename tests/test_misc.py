import pytest

from bot.scrapers.base import parse_price
from bot.scrapers.japan import fromjapan_url, parse_mercari_price
from bot.services.fx_wise import _extract_wise_rate
from bot.services.knowledge import split_sections
from bot.services.price_monitor import trend_pct, window_prices


@pytest.mark.parametrize(
    "text,expected",
    [
        ("12,34 EUR", 12.34),
        ("EUR 9.99", 9.99),
        ("1.234,56 €", 1234.56),
        ("1,234.56", 1234.56),
        ("\xa015,00\xa0€", 15.0),
        ("pas de prix", None),
        ("", None),
    ],
)
def test_parse_price(text, expected):
    if expected is None:
        assert parse_price(text) is None
    else:
        assert parse_price(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text,amount,currency",
    [
        ("€56.93", 56.93, "EUR"),
        ("¥135,999", 135999.0, "JPY"),     # virgule = milliers en yen
        ("12,000円", 12000.0, "JPY"),
        ("€1.234,56", 1234.56, "EUR"),
        ("", None, "JPY"),
    ],
)
def test_parse_mercari_price(text, amount, currency):
    a, c = parse_mercari_price(text)
    assert c == currency
    if amount is None:
        assert a is None
    else:
        assert a == pytest.approx(amount)


def test_fromjapan_url():
    assert fromjapan_url("m12345") == "https://www.fromjapan.co.jp/japan/en/mercari/item/m12345"


def test_extract_wise_rate_list():
    assert _extract_wise_rate([{"rate": 0.0062}]) == pytest.approx(0.0062)


def test_extract_wise_rate_obj():
    assert _extract_wise_rate({"value": 0.0061}) == pytest.approx(0.0061)


def test_extract_wise_rate_none():
    assert _extract_wise_rate({"foo": "bar"}) is None


def test_split_sections():
    md = "# Titre\nintro\n## A\ncorps A\n## B\ncorps B"
    secs = split_sections(md, "doc")
    titles = [s.title for s in secs]
    assert "A" in titles and "B" in titles
    a = next(s for s in secs if s.title == "A")
    assert "corps A" in a.body


def test_trend_pct():
    assert trend_pct([100, 110]) == pytest.approx(0.10)
    assert trend_pct([100]) is None
    assert trend_pct([0, 10]) is None


def test_window_prices_keeps_all_when_recent():
    rows = [
        {"price": 10, "recorded_at": "2099-01-01 00:00:00"},
        {"price": 12, "recorded_at": "2099-01-02 00:00:00"},
    ]
    assert window_prices(rows, 7) == [10.0, 12.0]
