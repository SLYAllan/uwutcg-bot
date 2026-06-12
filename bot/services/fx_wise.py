"""Taux de change EUR → JPY depuis Wise, avec cache et fallback (§3.3).

Sens du taux : **1 EUR = `rate` JPY** (≈ 185), comme affiché partout (banques, Wise).
L'ancien sens JPY→EUR (≈ 0.0054) était illisible et perdait de la précision.

Source primaire : endpoint public qui alimente le widget de taux Wise.
Fallback (clairement étiqueté) : API Frankfurter (BCE, gratuite, sans clé).
NB : l'ancien fallback exchangerate.host exige désormais une clé API → remplacé.

Le taux est mis en cache (TTL) et réutilisé par /convert et le calculateur.
La logique de cache et de parsing est pure → testable ; seul le fetch touche le réseau.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from bot.scrapers.base import ScrapeClient

log = logging.getLogger(__name__)

WISE_URL = "https://wise.com/rates/live?source=EUR&target=JPY"
FALLBACK_URL = "https://api.frankfurter.dev/v1/latest?from=EUR&to=JPY"
CACHE_TTL = 3600.0  # 1 h

# Plausibilité d'un taux EUR→JPY (historiquement ~90-200) : tout taux hors plage
# signale une réponse inversée (JPY→EUR ≈ 0.0054) ou cassée → rejeté.
RATE_MIN, RATE_MAX = 50.0, 1000.0


@dataclass
class FxRate:
    rate: float          # 1 EUR = `rate` JPY
    source: str          # 'wise' | 'fallback:frankfurter.app'
    fetched_at: float

    def jpy_to_eur(self, jpy: float) -> float:
        return jpy / self.rate if self.rate else 0.0

    def eur_to_jpy(self, eur: float) -> float:
        return eur * self.rate

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
            raise RuntimeError("Impossible de récupérer un taux EUR→JPY (Wise + fallback KO).")
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
            rate = float(data["rates"]["JPY"])
            if not _plausible(rate):
                log.error("Fallback FX : taux EUR→JPY implausible (%s), rejeté.", rate)
                return None
            return FxRate(
                rate=rate, source="fallback:frankfurter.app", fetched_at=time.time()
            )
        except Exception as exc:  # noqa: BLE001
            log.error("Fallback FX KO : %s", exc)
        return None


def _plausible(rate: float) -> bool:
    return RATE_MIN <= rate <= RATE_MAX


def _extract_wise_rate(data: dict | list) -> float | None:
    """Extrait le taux EUR→JPY d'une réponse Wise (formats possibles : liste ou objet).

    Rejette les valeurs implausibles (taux inversé JPY→EUR, réponse cassée).
    Pure → testable avec des fixtures.
    """
    candidates: list[float] = []
    if isinstance(data, list) and data:
        first = data[0]
        for key in ("rate", "value", "midMarketRate"):
            if isinstance(first, dict) and key in first:
                candidates.append(float(first[key]))
                break
    if isinstance(data, dict):
        for key in ("rate", "value", "midMarketRate"):
            if key in data:
                candidates.append(float(data[key]))
                break
    for rate in candidates:
        if _plausible(rate):
            return rate
        log.error("Wise : taux EUR→JPY implausible (%s), rejeté.", rate)
    return None
