"""Scraper eBay.

- Annonces ACTIVES (§3.1) : API Browse officielle (gratuite, OAuth client credentials).
  C'est la voie privilégiée — propre et stable.
- Ventes RÉUSSIES (§3.2) : l'API sold (Marketplace Insights) demande une approbation
  difficile → on scrape les pages "sold/completed" (LH_Sold=1&LH_Complete=1).

⚠️ VÉRIFIER EN PROD : les sélecteurs HTML des pages "sold" changent régulièrement.
   Ils sont regroupés dans SOLD_SELECTORS ci-dessous pour correction facile.
"""
from __future__ import annotations

import base64
import logging
import time
from statistics import median
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from bot.config import get_settings
from bot.scrapers.base import Listing, ScrapeClient, SoldStats, parse_price

log = logging.getLogger(__name__)

# --- Constantes API Browse ---------------------------------------------------
BROWSE_SEARCH = "/buy/browse/v1/item_summary/search"
OAUTH_TOKEN = "/identity/v1/oauth2/token"
OAUTH_SCOPE = "https://api.ebay.com/oauth/api_scope"

# --- ⚠️ Sélecteurs page "sold" (VÉRIFIER EN PROD) ----------------------------
SOLD_SELECTORS = {
    "item": "li.s-item",
    "title": ".s-item__title",
    "price": ".s-item__price",
    "date": ".s-item__caption--signal, .POSITIVE",
    "link": "a.s-item__link",
    "image": ".s-item__image-img",
}
EBAY_FR_BASE = "https://www.ebay.fr"


class EbayScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client
        self.settings = get_settings()
        self._token: str | None = None
        self._token_exp: float = 0.0

    # --- OAuth (client credentials) ------------------------------------------
    async def _get_app_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        creds = f"{self.settings.ebay_app_id}:{self.settings.ebay_cert_id}".encode()
        auth = base64.b64encode(creds).decode()
        await self.client.start()
        resp = await self.client._http.post(  # type: ignore[union-attr]
            f"{self.settings.ebay_oauth_base}{OAUTH_TOKEN}",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials", "scope": OAUTH_SCOPE},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 7200))
        log.info("Token eBay Browse rafraîchi (expire dans %ss)", data.get("expires_in"))
        return self._token

    # --- Annonces actives (API Browse) ---------------------------------------
    async def search_active(
        self, query: str, *, limit: int = 25, max_price: float | None = None
    ) -> list[Listing]:
        token = await self._get_app_token()
        params: dict = {"q": query, "limit": str(limit), "sort": "newlyListed"}
        flt = ["buyingOptions:{FIXED_PRICE|AUCTION}"]
        if max_price is not None:
            flt.append(f"price:[..{max_price}],priceCurrency:EUR")
        params["filter"] = ",".join(flt)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.settings.ebay_marketplace_id,
            "Content-Type": "application/json",
        }
        url = f"{self.settings.ebay_oauth_base}{BROWSE_SEARCH}"
        data = await self.client.get_json(url, params=params, headers=headers)
        out: list[Listing] = []
        for it in data.get("itemSummaries", []) or []:
            price = it.get("price", {}) or {}
            img = (it.get("image", {}) or {}).get("imageUrl")
            out.append(
                Listing(
                    key=str(it.get("itemId", it.get("itemWebUrl", ""))),
                    platform="ebay",
                    title=it.get("title", "(sans titre)"),
                    price=float(price["value"]) if price.get("value") else None,
                    currency=price.get("currency", "EUR"),
                    url=it.get("itemWebUrl", ""),
                    condition=it.get("condition"),
                    seller=(it.get("seller", {}) or {}).get("username"),
                    image_url=img,
                    item_id=str(it.get("legacyItemId") or it.get("itemId", "")),
                    extra={"buyingOptions": it.get("buyingOptions", [])},
                )
            )
        return out

    # --- Ventes réussies (scrape sold/completed) -----------------------------
    async def search_sold(self, query: str, *, limit: int = 40) -> SoldStats:
        url = (
            f"{EBAY_FR_BASE}/sch/i.html?_nkw={quote_plus(query)}"
            f"&LH_Sold=1&LH_Complete=1&_ipg={limit}"
        )
        html = await self.client.render(url, wait_selector=SOLD_SELECTORS["item"])
        listings = self._parse_sold(html)
        prices = [x.price for x in listings if x.price is not None]
        return SoldStats(
            query=query,
            platform="ebay",
            count=len(listings),
            min_price=min(prices) if prices else None,
            median_price=median(prices) if prices else None,
            max_price=max(prices) if prices else None,
            samples=listings[:10],
        )

    def _parse_sold(self, html: str) -> list[Listing]:
        tree = HTMLParser(html)
        out: list[Listing] = []
        for node in tree.css(SOLD_SELECTORS["item"]):
            title_n = node.css_first(SOLD_SELECTORS["title"])
            price_n = node.css_first(SOLD_SELECTORS["price"])
            link_n = node.css_first(SOLD_SELECTORS["link"])
            title = title_n.text(strip=True) if title_n else ""
            if not title or title.lower().startswith("shop on ebay"):
                continue
            out.append(
                Listing(
                    key=link_n.attributes.get("href", title) if link_n else title,
                    platform="ebay",
                    title=title,
                    price=parse_price(price_n.text(strip=True) if price_n else ""),
                    url=link_n.attributes.get("href", "") if link_n else "",
                )
            )
        return out


def build_cart_url(item_id: str, domain: str = "ebay.fr") -> str:
    """Lien d'ajout au panier eBay pour un article Buy-It-Now (§3.10, bouton lien direct).

    ⚠️ VÉRIFIER EN PROD via Playwright MCP : le pattern cart.payments.ebay.* évolue.
    Pour les enchères pures (non éligibles au panier), utiliser l'URL d'annonce à la place.
    """
    tld = domain.split("ebay.", 1)[-1] if "ebay." in domain else "fr"
    return f"https://cart.payments.ebay.{tld}/sc/add?item={item_id}&quantity=1"
