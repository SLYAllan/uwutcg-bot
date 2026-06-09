"""Smoke-test des scrapers (hors Discord). Lance chaque source et affiche le résultat.

Usage :
    python -m scripts.smoke_scrapers              # tout
    python -m scripts.smoke_scrapers ebay vinted  # sélection

Sources : ebay (API Browse), ebay_sold, vinted, cardmarket, japan, riftcodex, fx.
Chaque test est isolé : une source qui échoue n'arrête pas les autres.
"""
from __future__ import annotations

import asyncio
import sys
import traceback

from bot.scrapers.base import ScrapeClient
from bot.scrapers.cardmarket import CardmarketScraper
from bot.scrapers.ebay import EbayScraper
from bot.scrapers.japan import MercariScraper
from bot.scrapers.riftcodex import RiftcodexScraper
from bot.scrapers.vinted import VintedScraper
from bot.services.fx_wise import WiseFx

QUERY = "pikachu"


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def ko(name: str, exc: Exception) -> None:
    print(f"  ❌ {name} : {type(exc).__name__}: {exc}")
    traceback.print_exc(limit=1)


async def t_ebay(c: ScrapeClient):
    s = EbayScraper(c)
    items = await s.search_active(QUERY, limit=5)
    ok(f"eBay Browse: {len(items)} annonces actives")
    for it in items[:3]:
        print(f"     - {it.price} {it.currency} | {it.title[:60]} | id={it.item_id}")


async def t_ebay_sold(c: ScrapeClient):
    s = EbayScraper(c)
    stats = await s.search_sold(QUERY, limit=20)
    ok(f"eBay sold: {stats.count} ventes, médiane {stats.median_price}")


async def t_vinted(c: ScrapeClient):
    s = VintedScraper(c)
    items = await s.search_active(QUERY, per_page=5)
    ok(f"Vinted: {len(items)} annonces")
    for it in items[:3]:
        print(f"     - {it.price} {it.currency} | {it.title[:60]}")


async def t_cardmarket(c: ScrapeClient):
    s = CardmarketScraper(c)
    items = await s.search(QUERY, limit=5)
    ok(f"Cardmarket search: {len(items)} produits")
    for it in items[:3]:
        print(f"     - {it.title[:70]}")


async def t_japan(c: ScrapeClient):
    s = MercariScraper(c)
    items = await s.search(QUERY, limit=5)
    ok(f"Mercari JP: {len(items)} annonces")
    for it in items[:3]:
        fj = it.extra.get("fromjapan_url", "")
        print(f"     - {it.price} {it.currency} | {it.title[:40]} | FromJapan: {fj}")


async def t_riftcodex(c: ScrapeClient):
    s = RiftcodexScraper(c)
    res = await s.search("Jinx", limit=3)
    ok(f"Riftcodex: {s.count} cartes, top = {res[0].name if res else None}")


async def t_fx(c: ScrapeClient):
    fx = WiseFx(c)
    r = await fx.get_rate()
    ok(f"FX JPY->EUR: {r.rate} ({r.source})")


TESTS = {
    "ebay": t_ebay,
    "ebay_sold": t_ebay_sold,
    "vinted": t_vinted,
    "cardmarket": t_cardmarket,
    "japan": t_japan,
    "riftcodex": t_riftcodex,
    "fx": t_fx,
}


async def main(selected: list[str]) -> None:
    c = ScrapeClient()
    try:
        for name in selected:
            print(f"\n=== {name} ===")
            try:
                await TESTS[name](c)
            except Exception as exc:  # noqa: BLE001
                ko(name, exc)
    finally:
        await c.close()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a in TESTS] or list(TESTS)
    asyncio.run(main(args))
