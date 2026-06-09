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
import re
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

# --- Sélecteurs (vérifiés en live 2026-06-09 pour la recherche) --------------
# Un lien produit réel a la forme /Products/<Categorie>/<Set>/<Nom> (≥ 3 segments
# après /Products/). La nav catégorie (/Products/Singles) est ainsi exclue.
PRODUCT_HREF = re.compile(r"/Products/[^/]+/[^/]+/[^/]+")
# Le texte du lien produit ressemble à "Dracaufeu  (LOR TG03)À partir de18,00 €".
PRICE_SPLIT = re.compile(r"À partir de", re.IGNORECASE)

# ⚠️ La page produit détaillée (offres/conditions/langues) garde des sélecteurs à
#    VÉRIFIER EN PROD — la structure des lignes d'offres n'a pas été revalidée en live.
CM_SELECTORS = {
    "offer_row": ".article-row",
    "offer_price": ".price-container, .col-offer .price",
    "offer_condition": ".article-condition .badge, span[data-toggle='tooltip']",
    "offer_language": ".icon[data-original-title], .article-condition + span",
    "grade_badge": ".badge.professional-grading, .grading-badge",
}


# Stats de l'en-tête produit (libellés FR stables, validés en live 2026-06-09).
CM_STATS = {
    "total_available": re.compile(r"disponibles?\s+(\d[\d\s.]*)", re.IGNORECASE),
    "trend": re.compile(r"Tendance des prix\s+([\d.,\s]+?)\s*€", re.IGNORECASE),
    "avg_30d": re.compile(r"Prix moyen 30\s*jours\s+([\d.,\s]+?)\s*€", re.IGNORECASE),
    "avg_7d": re.compile(r"Prix moyen 7\s*jours\s+([\d.,\s]+?)\s*€", re.IGNORECASE),
    "from": re.compile(r"\bDe\s+([\d.,\s]+?)\s*€", re.IGNORECASE),
}


@dataclass
class ProductDetail:
    """Synthèse détaillée d'un produit Cardmarket (§3.4).

    `total_available` vient de l'en-tête (vrai total, ex. 402). `offers_count`, la
    répartition état/langue et gradées/raw ne portent que sur les offres AFFICHÉES
    (page 1, ~50) — Cardmarket ne charge pas tout d'un coup.
    """

    name: str
    url: str
    lowest_price: float | None
    offers_count: int               # offres affichées (page 1)
    total_available: int | None = None   # vrai total (en-tête)
    trend_price: float | None = None
    avg_7d: float | None = None
    avg_30d: float | None = None
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
        seen: set[str] = set()
        for link in tree.css("a"):
            href = link.attributes.get("href", "")
            if not href or "Search" in href or not PRODUCT_HREF.search(href):
                continue
            full = href if href.startswith("http") else f"https://www.cardmarket.com{href}"
            if full in seen:
                continue
            seen.add(full)
            # Le texte mélange nom et "À partir deXX,XX €" → on sépare.
            raw = link.text(strip=True)
            parts = PRICE_SPLIT.split(raw, maxsplit=1)
            title = parts[0].strip()
            price = parse_price(parts[1]) if len(parts) > 1 else None
            if not title:
                continue
            out.append(
                Listing(key=full, platform="cardmarket", title=title, price=price, url=full)
            )
            if len(out) >= limit:
                break
        return out

    # --- détail produit (monitor §3.4) ---------------------------------------
    async def product_detail(self, product_url: str) -> ProductDetail:
        html = await self.client.render(product_url, wait_selector="body", min_interval=6.0)
        tree = HTMLParser(html)
        name_n = tree.css_first("h1")
        name = name_n.text(strip=True) if name_n else product_url
        page_text = (tree.css_first("body").text(separator=" ", strip=True)
                     if tree.css_first("body") else "")

        # 1) Stats de l'en-tête (VRAI total + tendance + moyennes) — non tronquées.
        total_available = None
        m = CM_STATS["total_available"].search(page_text)
        if m:
            total_available = int(re.sub(r"\D", "", m.group(1)) or 0)
        trend = self._stat("trend", page_text)
        avg30 = self._stat("avg_30d", page_text)
        avg7 = self._stat("avg_7d", page_text)
        from_price = self._stat("from", page_text)

        # 2) Offres affichées (page 1, ~50) pour le prix mini + répartition partielle.
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

        # Prix mini : les offres étant triées par prix croissant, le mini de la page 1
        # EST le mini global ; à défaut on retombe sur le "De X €" de l'en-tête.
        lowest = min(prices) if prices else from_price

        return ProductDetail(
            name=name,
            url=product_url,
            lowest_price=lowest,
            offers_count=len(prices),
            total_available=total_available,
            trend_price=trend,
            avg_7d=avg7,
            avg_30d=avg30,
            by_condition=by_cond,
            by_language=by_lang,
            graded_count=graded,
            raw_count=raw,
        )

    @staticmethod
    def _stat(key: str, text: str) -> float | None:
        m = CM_STATS[key].search(text)
        return parse_price(m.group(1)) if m else None

    # --- prix le plus bas (EUR) pour une carte -------------------------------
    async def lowest_price(self, query: str, *, game: str = "pokemon") -> float | None:
        """Prix « à partir de » EUR de la 1re carte correspondante. None si introuvable.

        S'appuie sur la page de recherche (validée en live), pas sur la page produit.
        """
        results = await self.search(query, limit=1, game=game)
        return results[0].price if results else None

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
