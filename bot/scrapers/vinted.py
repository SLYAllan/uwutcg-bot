"""Scraper Vinted (§3.1).

Pas d'API publique : on utilise l'endpoint JSON interne du catalogue
`/api/v2/catalog/items`. Il faut d'abord récupérer le cookie de session
(`_vinted_fr_session` + `access_token_web`) en visitant le site, puis le réutiliser
et le rafraîchir à l'expiration.

⚠️ VÉRIFIER EN PROD : noms de cookies, chemin de l'endpoint et clés JSON évoluent.
   Tout est regroupé dans VINTED_KEYS pour correction facile.
"""
from __future__ import annotations

import logging

import httpx

from bot.config import get_settings
from bot.scrapers.base import Listing, ScrapeClient

log = logging.getLogger(__name__)

# --- ⚠️ Points sensibles (VÉRIFIER EN PROD) ----------------------------------
VINTED_KEYS = {
    "catalog_path": "/api/v2/catalog/items",
    "items_field": "items",
    "id": "id",
    "title": "title",
    "price_obj": "price",          # {"amount": "12.0", "currency_code": "EUR"}
    "price_amount": "amount",
    "price_currency": "currency_code",
    "url": "url",
    "photo": "photo",              # {"url": ...}
    "brand": "brand_title",
    "status": "status",            # condition
    "seller": "user",              # {"login": ...}
    "session_cookie": "_vinted_fr_session",
    "access_cookie": "access_token_web",
}


class VintedScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client
        self.settings = get_settings()
        self._cookies: dict[str, str] = {}
        self._domain = self.settings.vinted_domain

    @property
    def base_url(self) -> str:
        return f"https://{self._domain}"

    async def _ensure_session(self, force: bool = False) -> None:
        """Récupère/rafraîchit les cookies de session en visitant la home."""
        if self._cookies and not force:
            return
        # cookie pré-fourni via .env ?
        if self.settings.vinted_session_cookie and not force:
            self._cookies = self._parse_cookie_header(self.settings.vinted_session_cookie)
            if self._cookies:
                return
        await self.client.start()
        resp = await self.client.get(self.base_url, min_interval=5.0)
        jar = resp.cookies
        self._cookies = {k: jar.get(k) for k in jar.keys()}  # type: ignore[misc]
        log.info("Session Vinted initialisée (%d cookies)", len(self._cookies))

    @staticmethod
    def _parse_cookie_header(header: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for part in header.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                out[k] = v
        return out

    async def search_active(
        self, query: str, *, per_page: int = 24, max_price: float | None = None
    ) -> list[Listing]:
        await self._ensure_session()
        params: dict = {
            "search_text": query,
            "per_page": str(per_page),
            "order": "newest_first",
        }
        if max_price is not None:
            params["price_to"] = str(max_price)
            params["currency"] = "EUR"
        url = f"{self.base_url}{VINTED_KEYS['catalog_path']}"
        headers = {"Accept": "application/json", "Referer": self.base_url}
        try:
            resp = await self.client.get(
                url, params=params, headers={**headers, **self._cookie_header()}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):  # token expiré → refresh une fois
                log.info("Token Vinted expiré, rafraîchissement…")
                await self._ensure_session(force=True)
                resp = await self.client.get(
                    url, params=params, headers={**headers, **self._cookie_header()}
                )
            else:
                raise
        data = resp.json()
        return self._parse_items(data)

    def _cookie_header(self) -> dict[str, str]:
        if not self._cookies:
            return {}
        return {"Cookie": "; ".join(f"{k}={v}" for k, v in self._cookies.items())}

    def _parse_items(self, data: dict) -> list[Listing]:
        k = VINTED_KEYS
        out: list[Listing] = []
        for it in data.get(k["items_field"], []) or []:
            price_obj = it.get(k["price_obj"]) or {}
            if isinstance(price_obj, (int, float, str)):  # ancien format plat
                amount, currency = price_obj, "EUR"
            else:
                amount = price_obj.get(k["price_amount"])
                currency = price_obj.get(k["price_currency"], "EUR")
            photo = it.get(k["photo"]) or {}
            seller = it.get(k["seller"]) or {}
            item_id = str(it.get(k["id"], ""))
            out.append(
                Listing(
                    key=item_id,
                    platform="vinted",
                    title=it.get(k["title"], "(sans titre)"),
                    price=float(amount) if amount not in (None, "") else None,
                    currency=currency or "EUR",
                    url=it.get(k["url"]) or f"{self.base_url}/items/{item_id}",
                    condition=it.get(k["status"]),
                    seller=seller.get("login") if isinstance(seller, dict) else None,
                    image_url=photo.get("url") if isinstance(photo, dict) else None,
                    item_id=item_id,
                )
            )
        return out

    def item_url(self, item_id: str) -> str:
        """URL d'article Vinted pour le bouton lien direct (§3.10)."""
        return f"{self.base_url}/items/{item_id}"
