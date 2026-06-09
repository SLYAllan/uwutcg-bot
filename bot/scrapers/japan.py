"""Scraper sourcing Japon (§3.6) : Mercari JP / Yahoo Auctions via Buyee.

On passe par les pages publiques de Buyee (proxy d'achat) qui agrègent Mercari/Yahoo
et affichent les prix en JPY → simple à parser et déjà côté "achat depuis l'étranger".

⚠️ VÉRIFIER EN PROD : sélecteurs Buyee volatils, regroupés dans BUYEE_SELECTORS.
   Prix renvoyés en JPY (currency='JPY') — la conversion € se fait dans services/arbitrage.
"""
from __future__ import annotations

import logging
from urllib.parse import quote

from selectolax.parser import HTMLParser

from bot.scrapers.base import Listing, ScrapeClient, parse_price

log = logging.getLogger(__name__)

BUYEE_BASE = "https://buyee.jp"

# --- ⚠️ Sélecteurs (VÉRIFIER EN PROD) ----------------------------------------
BUYEE_SELECTORS = {
    "item": "li.itemCard, .g-thumbnail__outer",
    "title": ".itemCard__itemName, .g-thumbnail__caption",
    "price": ".g-price, .itemCard__price",
    "link": "a",
    "image": "img",
}


class JapanScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client

    async def search_mercari(self, query: str, *, limit: int = 20) -> list[Listing]:
        url = f"{BUYEE_BASE}/mercari/search?keyword={quote(query)}"
        return await self._search(url, limit, source="mercari")

    async def search_yahoo(self, query: str, *, limit: int = 20) -> list[Listing]:
        url = f"{BUYEE_BASE}/yahoo/search?keyword={quote(query)}"
        return await self._search(url, limit, source="yahoo")

    async def _search(self, url: str, limit: int, *, source: str) -> list[Listing]:
        html = await self.client.render(url, wait_selector="body", min_interval=6.0)
        tree = HTMLParser(html)
        out: list[Listing] = []
        for node in tree.css(BUYEE_SELECTORS["item"])[:limit]:
            title_n = node.css_first(BUYEE_SELECTORS["title"])
            price_n = node.css_first(BUYEE_SELECTORS["price"])
            link_n = node.css_first(BUYEE_SELECTORS["link"])
            img_n = node.css_first(BUYEE_SELECTORS["image"])
            if not title_n:
                continue
            href = link_n.attributes.get("href", "") if link_n else ""
            full = href if href.startswith("http") else f"{BUYEE_BASE}{href}"
            out.append(
                Listing(
                    key=full,
                    platform=f"japan:{source}",
                    title=title_n.text(strip=True),
                    price=parse_price(price_n.text(strip=True)) if price_n else None,
                    currency="JPY",
                    url=full,
                    image_url=img_n.attributes.get("src") if img_n else None,
                )
            )
        return out

    async def cheapest(self, query: str) -> Listing | None:
        """Renvoie l'annonce JP la moins chère (Mercari + Yahoo) pour l'arbitrage."""
        results: list[Listing] = []
        for fn in (self.search_mercari, self.search_yahoo):
            try:
                results.extend(await fn(query, limit=15))
            except Exception as exc:  # noqa: BLE001 - une source peut tomber
                log.warning("Source JP indisponible (%s): %s", fn.__name__, exc)
        priced = [r for r in results if r.price is not None]
        return min(priced, key=lambda r: r.price) if priced else None
