"""Détecteur de sous-évaluation / deal sniper (§4, §5). Logique pure → testée.

Compare le prix d'une annonce au prix marché de référence (médiane des ventes /
tendance Cardmarket) et calcule l'écart en %. Sert au deal sniper (§5) et aux
boutons « calcule ma marge ».
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UndervalueResult:
    listing_price: float
    market_price: float
    discount_pct: float      # part SOUS le marché (0.25 = 25 % moins cher)
    is_deal: bool


def below_market_pct(listing_price: float, market_price: float) -> float:
    """Écart relatif sous le marché. 0.25 = annonce 25 % moins chère que le marché."""
    if market_price <= 0:
        return 0.0
    return (market_price - listing_price) / market_price


def evaluate(
    listing_price: float, market_price: float, deal_threshold: float
) -> UndervalueResult:
    discount = below_market_pct(listing_price, market_price)
    return UndervalueResult(
        listing_price=listing_price,
        market_price=market_price,
        discount_pct=discount,
        is_deal=discount >= deal_threshold,
    )


# --- Heuristique anti-arnaque (§5) -------------------------------------------
def looks_like_scam(listing_price: float, market_price: float, hard_floor_pct: float = 0.65) -> bool:
    """Flag les annonces anormalement basses (souvent fake/scam).

    True si l'annonce est >= `hard_floor_pct` SOUS le marché (défaut 65 %).
    """
    return below_market_pct(listing_price, market_price) >= hard_floor_pct
