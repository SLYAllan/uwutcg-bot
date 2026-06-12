"""Sourcing Japon (§3.6) : scrape **Mercari JP en direct** + lien d'achat **FromJapan**.

Allan source via FromJapan (proxy d'achat). On scanne donc Mercari JP directement
(jp.mercari.com, SPA React → Playwright avec scroll), et chaque annonce porte un lien
**FromJapan** vers l'article (`/japan/en/mercari/item/<id>`) : un tap → page de commande
FromJapan (la validation/paiement reste côté Allan, comme l'exige la loi).

⚠️ VÉRIFIER EN PROD : Mercari JP affiche la devise selon la géo du serveur (€ depuis l'UE,
   ¥ depuis le Japon) → la devise est détectée au symbole. Sélecteurs validés en live le
   2026-06-09 (a[data-testid=thumbnail-link]).
"""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

from selectolax.parser import HTMLParser

from bot.scrapers.base import Listing, ScrapeClient, parse_price

log = logging.getLogger(__name__)

MERCARI_BASE = "https://jp.mercari.com"
FROMJAPAN_ITEM = "https://www.fromjapan.co.jp/japan/en/mercari/item/{id}"

# Sélecteurs Mercari (validés en live 2026-06-09)
THUMB_LINK = "a[data-testid=thumbnail-link]"
ITEM_ID_RE = re.compile(r"/item/(m\d+)")

# Montant ancré au symbole monétaire : groupes de milliers stricts (virgule, virgule
# pleine chasse ，, point, espaces y compris insécables via \s) pour ne JAMAIS avaler
# les chiffres du titre ou des badges (« いいね3 », « 残り1点 »).
_SEP = r"[,，.\s]"
_NUM = rf"\d{{1,3}}(?:{_SEP}\d{{3}})*(?:[.,]\d{{1,2}})?"
_YEN_NUM = rf"\d{{1,3}}(?:{_SEP}\d{{3}})*"  # le yen n'a pas de décimales
# Symbole AVANT le montant testé en premier : dans « titre 151 €56.93 », la forme
# suffixe matcherait « 151 € » (plus tôt dans la chaîne) et prendrait le titre pour prix.
_EUR_RES = (re.compile(rf"€\s*({_NUM})"), re.compile(rf"({_NUM})\s*€"))
_YEN_RES = (re.compile(rf"[¥￥]\s*({_YEN_NUM})"), re.compile(rf"({_YEN_NUM})\s*円"))


def parse_mercari_price(text: str) -> tuple[float | None, str]:
    """Renvoie (montant, devise) extrait du texte d'une vignette Mercari.

    Le texte peut contenir le titre et des badges : le montant est ancré au symbole
    (€, ¥/￥, 円) — sans symbole, pas de prix fiable → None (un chiffre du titre
    pris pour un prix fausserait le tracking et l'arbitrage).
    """
    if not text:
        return None, "JPY"
    for rx in _EUR_RES:
        m = rx.search(text)
        if m:
            return parse_price(m.group(1)), "EUR"
    for rx in _YEN_RES:
        m = rx.search(text)
        if m:
            digits = re.sub(r"\D", "", m.group(1))
            return (float(digits) if digits else None), "JPY"
    return None, "JPY"


class MercariScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client

    async def search(self, query: str, *, limit: int = 20) -> list[Listing]:
        url = f"{MERCARI_BASE}/search?keyword={quote(query)}"
        html = await self.client.render(
            url, wait_selector=THUMB_LINK, scroll=2, locale="ja-JP", min_interval=6.0,
            timeout_ms=45000,
        )
        tree = HTMLParser(html)
        out: list[Listing] = []
        seen: set[str] = set()
        for a in tree.css(THUMB_LINK):
            href = a.attributes.get("href", "")
            m = ITEM_ID_RE.search(href)
            if not m:
                continue
            item_id = m.group(1)
            if item_id in seen:
                continue
            seen.add(item_id)
            img = a.css_first("img")
            name = (img.attributes.get("alt", "") if img else "") or a.text(strip=True)
            name = re.sub(r"のサムネイル$", "", name).strip()  # suffixe "thumbnail of"
            price, currency = parse_mercari_price(a.text(strip=True))
            out.append(
                Listing(
                    key=item_id,
                    platform="mercari",
                    title=name[:200] or "(sans titre)",
                    price=price,
                    currency=currency,
                    url=f"{MERCARI_BASE}/item/{item_id}",
                    item_id=item_id,
                    image_url=img.attributes.get("src") if img else None,
                    extra={"fromjapan_url": fromjapan_url(item_id)},
                )
            )
            if len(out) >= limit:
                break
        return out

    async def cheapest(self, query: str) -> Listing | None:
        """Annonce Mercari la moins chère pour l'arbitrage."""
        try:
            results = await self.search(query, limit=20)
        except Exception as exc:  # noqa: BLE001
            log.warning("Mercari indisponible : %s", exc)
            return None
        priced = [r for r in results if r.price is not None]
        return min(priced, key=lambda r: r.price) if priced else None


def fromjapan_url(mercari_item_id: str) -> str:
    """Lien FromJapan vers l'article Mercari (page de commande FromJapan)."""
    return FROMJAPAN_ITEM.format(id=mercari_item_id)


# Alias rétro-compat (l'ancien nom JapanScraper pointait sur Buyee, désormais Mercari)
JapanScraper = MercariScraper
