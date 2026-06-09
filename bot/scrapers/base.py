"""Couche réseau anti-ban partagée par tous les scrapers.

Fournit :
- `ScrapeClient` : façade unique pour httpx (pages statiques / endpoints JSON) ET
  Playwright (pages protégées Cloudflare / JS lourd), avec :
    * rate-limiter PAR DOMAINE (intervalle minimal entre 2 hits)
    * jitter aléatoire
    * retry + backoff exponentiel (tenacity)
    * rotation de user-agents réalistes
    * pool Playwright partagé (un seul navigateur chromium, lazy-init)
- `Listing` / `SoldStats` : modèles de données communs renvoyés par les scrapers.

Aucune plateforme ne doit être interrogée plus souvent que nécessaire : chaque scraper
réutilise ce client et hérite donc du rate-limit. Les intervalles sont configurables.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

# User-agents réalistes (desktop récents). Étendre au besoin.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Intervalle minimal par défaut entre 2 requêtes vers le même domaine (secondes).
DEFAULT_MIN_INTERVAL = 3.0


def parse_price(text: str) -> float | None:
    """Extrait un float d'une chaîne prix, gère FR (1.234,56) et EN (1,234.56).

    Réutilisé par tous les scrapers. Renvoie None si rien d'exploitable.
    """
    if not text:
        return None
    m = re.search(r"(\d[\d\s.,]*)", text.replace("\xa0", " "))
    if not m:
        return None
    raw = m.group(1).strip().replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):  # virgule décimale (FR)
            raw = raw.replace(".", "").replace(",", ".")
        else:  # point décimal (EN)
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


@dataclass
class Listing:
    """Annonce normalisée renvoyée par les scrapers de tracking (§3.1)."""

    key: str                     # identifiant stable (id annonce ou hash URL) pour dédup
    platform: str
    title: str
    price: float | None
    currency: str = "EUR"
    url: str = ""
    condition: str | None = None
    seller: str | None = None
    image_url: str | None = None
    item_id: str | None = None   # id natif (eBay itemId, Vinted id…) pour les boutons
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SoldStats:
    """Synthèse de ventes réussies (§3.2)."""

    query: str
    platform: str
    count: int
    min_price: float | None
    median_price: float | None
    max_price: float | None
    currency: str = "EUR"
    samples: list[Listing] = field(default_factory=list)


class _DomainRateLimiter:
    """Garantit un intervalle minimal entre requêtes vers un même domaine, + jitter."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, domain: str) -> asyncio.Lock:
        if domain not in self._locks:
            self._locks[domain] = asyncio.Lock()
        return self._locks[domain]

    async def acquire(self, domain: str, min_interval: float) -> None:
        async with self._lock(domain):
            now = time.monotonic()
            last = self._last.get(domain, 0.0)
            wait = (last + min_interval) - now
            if wait > 0:
                await asyncio.sleep(wait)
            # jitter : 10–60 % de l'intervalle, pour casser la régularité
            await asyncio.sleep(random.uniform(0.1, 0.6) * min_interval)
            self._last[domain] = time.monotonic()


class ScrapeClient:
    """Façade réseau unique. Instancier une fois, injecter dans tous les scrapers."""

    def __init__(self, min_interval: float = DEFAULT_MIN_INTERVAL):
        self.min_interval = min_interval
        self._limiter = _DomainRateLimiter()
        self._http: httpx.AsyncClient | None = None
        # Playwright (lazy) — importé seulement quand nécessaire
        self._pw = None
        self._browser = None
        self._pw_lock = asyncio.Lock()

    # --- cycle de vie --------------------------------------------------------
    async def start(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(20.0),
                headers={"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"},
            )

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _domain(url: str) -> str:
        return httpx.URL(url).host or "unknown"

    def _ua(self) -> str:
        return random.choice(USER_AGENTS)

    # --- requêtes httpx (statique / JSON) ------------------------------------
    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        min_interval: float | None = None,
    ) -> httpx.Response:
        await self.start()
        await self._limiter.acquire(self._domain(url), min_interval or self.min_interval)
        h = {"User-Agent": self._ua(), **(headers or {})}
        resp = await self._http.get(url, params=params, headers=h)  # type: ignore[union-attr]
        resp.raise_for_status()
        return resp

    async def get_json(self, url: str, **kwargs) -> Any:
        resp = await self.get(url, **kwargs)
        return resp.json()

    # --- Playwright (Cloudflare / JS) ----------------------------------------
    async def _ensure_browser(self):
        """Lazy-init du navigateur chromium partagé + stealth si dispo."""
        async with self._pw_lock:
            if self._browser is not None:
                return self._browser
            from playwright.async_api import async_playwright  # import paresseux

            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            return self._browser

    async def render(
        self,
        url: str,
        *,
        wait_selector: str | None = None,
        min_interval: float | None = None,
        timeout_ms: int = 30000,
        scroll: int = 0,
        locale: str = "fr-FR",
    ) -> str:
        """Charge une page via Playwright et renvoie le HTML rendu.

        Utilisé pour Cardmarket (Cloudflare) et tout contenu JS lourd (SPA Mercari).
        `scroll` : nombre de défilements pour déclencher le lazy-loading (SPA).
        """
        await self._limiter.acquire(self._domain(url), min_interval or self.min_interval)
        browser = await self._ensure_browser()
        context = await browser.new_context(
            user_agent=self._ua(),
            locale=locale,
            viewport={"width": 1366, "height": 768},
        )
        try:
            try:
                from playwright_stealth import stealth_async  # optionnel
            except ImportError:
                stealth_async = None
            page = await context.new_page()
            if stealth_async:
                await stealth_async(page)
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=timeout_ms)
                except Exception:  # noqa: BLE001 - sélecteur volatil, on renvoie quand même
                    log.warning("Sélecteur %s absent sur %s", wait_selector, url)
            for _ in range(scroll):
                await page.mouse.wheel(0, 2200)
                await asyncio.sleep(random.uniform(0.8, 1.4))
            # petit délai aléatoire pour imiter un humain
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return await page.content()
        finally:
            await context.close()
