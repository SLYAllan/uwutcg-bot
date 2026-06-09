"""Détecteur de pic / vélocité (§3.9). Logique pure → testée.

S'appuie sur l'historique construit par le bot (price_history) + un compteur de volume.
Détecte : pic de PRIX (variation sur la médiane récente) et pic de VOLUME (intérêt soudain).
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass
class Spike:
    kind: str            # 'price' | 'volume'
    triggered: bool
    magnitude: float     # variation relative (ex. 0.22 = +22 %)
    detail: str = ""


def pct_change(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return (current - baseline) / baseline


def detect_price_spike(
    current_price: float, history_prices: list[float], threshold_pct: float
) -> Spike:
    """Pic si le prix courant dépasse la médiane de l'historique de `threshold_pct`."""
    if not history_prices:
        return Spike("price", False, 0.0, "historique vide")
    base = median(history_prices)
    change = pct_change(current_price, base)
    triggered = change >= threshold_pct
    return Spike(
        kind="price",
        triggered=triggered,
        magnitude=change,
        detail=f"courant {current_price:.2f} vs médiane {base:.2f} ({change:+.1%})",
    )


def detect_volume_spike(
    current_volume: int, history_volumes: list[int], factor: float
) -> Spike:
    """Pic si le volume courant ≥ `factor` × volume moyen historique."""
    if not history_volumes:
        return Spike("volume", False, 0.0, "historique vide")
    avg = sum(history_volumes) / len(history_volumes)
    if avg == 0:
        triggered = current_volume > 0
        mag = float(current_volume)
    else:
        mag = current_volume / avg
        triggered = mag >= factor
    return Spike(
        kind="volume",
        triggered=triggered,
        magnitude=mag,
        detail=f"courant {current_volume} vs moyenne {avg:.1f} (x{mag:.2f})",
    )
