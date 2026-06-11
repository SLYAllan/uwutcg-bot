"""Tracking Mercari (§3.1) : conversion JPY→EUR + filtre prix max + lien FromJapan."""
import pytest

from bot.cogs.tracking import TrackingCog
from bot.scrapers.base import Listing


class _FakeRate:
    rate = 0.006  # 1000 JPY = 6 €


class _FakeFx:
    async def get_rate(self):
        return _FakeRate()


class _FakeBot:
    fx = _FakeFx()


def _listing(price, currency="JPY", **extra):
    return Listing(
        key="m1", platform="mercari", title="t", price=price, currency=currency,
        url="https://jp.mercari.com/item/m1",
        extra={"fromjapan_url": "https://www.fromjapan.co.jp/japan/en/mercari/item/m1", **extra},
    )


def _cog():
    cog = TrackingCog.__new__(TrackingCog)  # sans __init__ (pas de boucle de polling)
    cog.bot = _FakeBot()
    return cog


@pytest.mark.asyncio
async def test_mercari_to_eur_converts_jpy():
    out = await _cog()._mercari_to_eur([_listing(10000.0)], None)
    assert out[0].price == pytest.approx(60.0)
    assert out[0].currency == "EUR"
    assert out[0].extra["price_jpy"] == 10000.0


@pytest.mark.asyncio
async def test_mercari_to_eur_filters_max_price():
    listings = [_listing(10000.0), _listing(1000.0)]  # 60 € et 6 €
    out = await _cog()._mercari_to_eur(listings, 10.0)
    assert len(out) == 1
    assert out[0].price == pytest.approx(6.0)


@pytest.mark.asyncio
async def test_mercari_to_eur_keeps_eur_as_is():
    out = await _cog()._mercari_to_eur([_listing(56.93, currency="EUR")], None)
    assert out[0].price == pytest.approx(56.93)
    assert "price_jpy" not in out[0].extra


def test_link_for_mercari_is_fromjapan():
    listing = _listing(1000.0)
    assert _cog()._link_for(listing) == "https://www.fromjapan.co.jp/japan/en/mercari/item/m1"
