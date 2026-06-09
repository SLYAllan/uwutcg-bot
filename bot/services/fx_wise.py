"""Taux de change JPY → EUR depuis Wise, avec cache et fallback (§3.3).

Source primaire : endpoint public qui alimente le widget de taux Wise.
Fallback (clairement étiqueté) : API FX gratuite (exchangerate.host).

Le taux est mis en cache (TTL) et réutilisé par /convert et le calculateur.
La logique de cache et de parsing est pure → testable ; seul le fetch touche le réseau.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from bot.scrapers.base import ScrapeClient

log = logging.getLogger(__name__)

WISE_URL = "https://wise.com/rates/live?source=JPY&target=EUR"
FALLBACK_URL = "https://api.exchangerate.host/latest?base=JPY&symbols=EUR"
CACHE_TTL = 3600.0  # 1 h


@dataclass
class FxRate:
    rate: float          # 1 JPY = `rate` EUR
    source: str          # 'wise' | 'fallback:exchangerate.host'
    fetched_at: float

    def jpy_to_eur(self, jpy: float) -> float:
        return jpy * self.rate

    def eur_to_jpy(self, eur: float) -> float:
        return eur / self.rate if self.rate else 0.0

    @property
    def is_fallback(self) -> bool:
        return self.source.startswith("fallback")


class WiseFx:
    def __init__(self, client: ScrapeClient):
        self.client = client
        self._cache: FxRate | None = None

    async def get_rate(self, force: bool = False) -> FxRate:
        if not force and self._cache and (time.time() - self._cache.fetched_at) < CACHE_TTL:
            return self._cache
        rate = await self._fetch_wise()
        if rate is None:
            rate = await self._fetch_fallback()
        if rate is None:
            if self._cache:  # mieux vaut un taux périmé que rien
                log.warning("FX indisponible, réutilisation du cache périmé.")
                return self._cache
            raise RuntimeError("Impossible de récupérer un taux JPY→EUR (Wise + fallback KO).")
        self._cache = rate
        return rate

    async def _fetch_wise(self) -> FxRate | None:
        try:
            data = await self.client.get_json(WISE_URL, min_interval=2.0)
            rate = _extract_wise_rate(data)
            if rate:
                return FxRate(rate=rate, source="wise", fetched_at=time.time())
        except Exception as exc:  # noqa: BLE001 - on bascule sur le fallback
            log.warning("Wise indisponible : %s", exc)
        return None

    async def _fetch_fallback(self) -> FxRate | None:
        try:
            data = await self.client.get_json(FALLBACK_URL, min_interval=2.0)
            rate = float(data["rates"]["EUR"])
            return FxRate(
                rate=rate, source="fallback:exchangerate.host", fetched_at=time.time()
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Fallback FX KO : %s", exc)
        return None


def _extract_wise_rate(data: dict | list) -> float | None:
    """Extrait le taux d'une réponse Wise (formats possibles : liste ou objet).

    ⚠️ VÉRIFIER EN PROD : structure exacte de l'endpoint Wise (clé 'rate'/'value').
    Pure → testable avec des fixtures.
    """
    if isinstance(data, list) and data:
        first = data[0]
        for key in ("rate", "value", "midMarketRate"):
            if isinstance(first, dict) and key in first:
                return float(first[key])
    if isinstance(data, dict):
        for key in ("rate", "value", "midMarketRate"):
            if key in data:
                return float(data[key])
    return None
