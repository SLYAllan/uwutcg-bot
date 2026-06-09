"""Scraper Cardmarket (§3.1, §3.2, §3.4).

Cloudflare + JS → rendu via Playwright (scrapers.base.render).
Trois usages :
- search() : annonces/offres de la recherche produit (tracking)
- product_detail() : prix mini, nb offres, répartition état/langue, gradées vs raw (monitor)
- price_trend() : historique/tendance de la page produit (ventes réussies)

⚠️ VÉRIFIER EN PROD : Cardmarket change souvent son HTML. Tous les sélecteurs sont
   regroupés dans CM_SELECTORS pour correction rapide (re-capture via Playwright MCP).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import median
from urllib.parse import quote

from selectolax.parser import HTMLParser

from bot.scrapers.base import Listing, ScrapeClient, SoldStats, parse_price

log = logging.getLogger(__name__)

CM_BASE = "https://www.cardmarket.com/fr"

# Slug de jeu dans l'URL Cardmarket. ⚠️ VÉRIFIER EN PROD le slug Riftbound exact.
CM_GAMES = {
    "pokemon": "Pokemon",
    "riftbound": "Riftbound",  # ⚠️ à confirmer (Cardmarket peut utiliser un autre libellé)
}

# --- ⚠️ Sélecteurs (VÉRIFIER EN PROD) ----------------------------------------
CM_SELECTORS = {
    "search_row": ".table-body > .row, .article-row",
    "product_link": "a[href*='/Products/']",
    "offer_row": ".article-row",
    "offer_price": ".price-container, .col-offer .price",
    "offer_condition": ".article-condition .badge, span[data-toggle='tooltip']",
    "offer_language": ".icon[data-original-title], .article-condition + span",
    "offer_seller": ".seller-name, .col-seller a",
    "info_min_price": "dd.h4, .info-list-container dd",
    "grade_badge": ".badge.professional-grading, .grading-badge",
}


@dataclass
class ProductDetail:
    """Synthèse détaillée d'un produit Cardmarket (§3.4)."""

    name: str
    url: str
    lowest_price: float | None
    offers_count: int
    by_condition: dict[str, int] = field(default_factory=dict)
    by_language: dict[str, int] = field(default_factory=dict)
    graded_count: int = 0
    raw_count: int = 0


class CardmarketScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client

    # --- recherche / tracking ------------------------------------------------
    async def search(self, query: str, *, limit: int = 20, game: str = "pokemon") -> list[Listing]:
        slug = CM_GAMES.get(game.lower(), "Pokemon")
        url = f"{CM_BASE}/{slug}/Products/Search?searchString={quote(query)}"
        html = await self.client.render(url, wait_selector="body", min_interval=6.0)
        tree = HTMLParser(html)
        out: list[Listing] = []
        for link in tree.css(CM_SELECTORS["product_link"])[:limit]:
            href = link.attributes.get("href", "")
            title = link.text(strip=True)
            if not href or not title:
                continue
            full = href if href.startswith("http") else f"https://www.cardmarket.com{href}"
            out.append(
                Listing(key=full, platform="cardmarket", title=title, price=None, url=full)
            )
        return out

    # --- détail produit (monitor §3.4) ---------------------------------------
    async def product_detail(self, product_url: str) -> ProductDetail:
        html = await self.client.render(product_url, wait_selector="body", min_interval=6.0)
        tree = HTMLParser(html)
        name_n = tree.css_first("h1")
        name = name_n.text(strip=True) if name_n else product_url

        prices: list[float] = []
        by_cond: dict[str, int] = {}
        by_lang: dict[str, int] = {}
        graded = raw = 0

        for row in tree.css(CM_SELECTORS["offer_row"]):
            price_n = row.css_first(CM_SELECTORS["offer_price"])
            price = parse_price(price_n.text(strip=True)) if price_n else None
            if price is not None:
                prices.append(price)
            cond_n = row.css_first(CM_SELECTORS["offer_condition"])
            cond = cond_n.text(strip=True) if cond_n else "?"
            by_cond[cond] = by_cond.get(cond, 0) + 1
            lang_n = row.css_first(CM_SELECTORS["offer_language"])
            lang = (lang_n.attributes.get("data-original-title") if lang_n else None) or "?"
            by_lang[lang] = by_lang.get(lang, 0) + 1
            if row.css_first(CM_SELECTORS["grade_badge"]):
                graded += 1
            else:
                raw += 1

        return ProductDetail(
            name=name,
            url=product_url,
            lowest_price=min(prices) if prices else None,
            offers_count=len(prices),
            by_condition=by_cond,
            by_language=by_lang,
            graded_count=graded,
            raw_count=raw,
        )

    # --- prix le plus bas (EUR) pour une carte -------------------------------
    async def lowest_price(self, query: str, *, game: str = "pokemon") -> float | None:
        """Prix mini EUR de la 1re carte correspondante (best effort). None si introuvable."""
        results = await self.search(query, limit=1, game=game)
        if not results:
            return None
        detail = await self.product_detail(results[0].url)
        return detail.lowest_price

    # --- tendance de prix / ventes (§3.2) ------------------------------------
    async def price_trend(self, query_or_url: str) -> SoldStats:
        """Récupère la tendance de prix de la page produit (approximation des ventes)."""
        if query_or_url.startswith("http"):
            url = query_or_url
        else:
            results = await self.search(query_or_url, limit=1)
            if not results:
                return SoldStats(query_or_url, "cardmarket", 0, None, None, None)
            url = results[0].url
        detail = await self.product_detail(url)
        # On expose le prix mini comme proxy ; l'historique réel est construit par le bot.
        lows = [detail.lowest_price] if detail.lowest_price else []
        return SoldStats(
            query=query_or_url,
            platform="cardmarket",
            count=detail.offers_count,
            min_price=detail.lowest_price,
            median_price=median(lows) if lows else None,
            max_price=detail.lowest_price,
        )
