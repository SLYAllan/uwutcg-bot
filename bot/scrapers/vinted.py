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


class VintedSessionError(RuntimeError):
    """La home a répondu, mais sans poser le cookie de session : l'API est inutilisable."""

    def __init__(self, cookies: list[str]):
        super().__init__(
            "Vinted n'a pas délivré de cookie access_token_web (tous les appels API "
            "répondront 401). La home a répondu 200 mais n'a posé que : "
            f"{', '.join(cookies) or 'aucun cookie'}. Cause probable : IP du serveur "
            "refusée (datacenter/VPS) ou page d'attente Cloudflare."
        )


class VintedScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client
        self.settings = get_settings()
        self._domain = self.settings.vinted_domain
        self._session_ready = False

    @property
    def base_url(self) -> str:
        return f"https://{self._domain}"

    async def _ensure_session(self, force: bool = False) -> None:
        """Visite la home pour que le cookie jar httpx récupère access_token_web.

        On délègue la gestion des cookies au jar partagé du ScrapeClient (httpx les
        renvoie automatiquement) — c'est ce qui fait passer l'API de 401 à 200.
        """
        if self._session_ready and not force:
            return
        await self.client.start()
        self._session_ready = False
        if force:
            # Le client httpx vit aussi longtemps que le bot (des semaines). Au bout d'un
            # moment sa session Vinted se périme et l'API répond 401 EN BOUCLE : re-visiter
            # la home ne répare rien, car le serveur voit un cookie déjà posé et n'en
            # redonne pas. Seul un processus neuf repartait. On jette donc les cookies
            # Vinted avant de re-visiter : même effet qu'un redémarrage, sans redémarrage.
            self._purge_cookies()
        await self.client.get(self.base_url, min_interval=5.0)
        # On VÉRIFIE que le cookie est bien là. Sans ce contrôle, une home qui répond 200
        # sans rien poser laissait le bot boucler en 401 à l'infini, avec un traceback
        # httpx qui ne disait pas ce qui manquait.
        if VINTED_KEYS["access_cookie"] not in self.client.cookies:
            raise VintedSessionError(sorted(self.client.cookies.keys()))
        self._session_ready = True
        log.info("Session Vinted initialisée (access_token_web obtenu)")

    def _purge_cookies(self) -> None:
        """Vide du jar partagé les seuls cookies Vinted (les autres scrapers y vivent)."""
        jar = self.client.cookies.jar
        root = self._domain.removeprefix("www.")
        for cookie in list(jar):
            if (cookie.domain or "").lstrip(".").endswith(root):
                jar.clear(cookie.domain, cookie.path, cookie.name)

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
            resp = await self.client.get(url, params=params, headers=headers)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):  # token expiré → re-visite la home
                log.info("Token Vinted expiré, rafraîchissement de la session…")
                await self._ensure_session(force=True)
                resp = await self.client.get(url, params=params, headers=headers)
            else:
                raise
        data = resp.json()
        return self._parse_items(data)

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
