"""Calculateur d'achat & seuil de rentabilité (§3.5). Logique 100 % pure → testée.

Modèle (micro-entreprise, franchise de TVA, vente de marchandises BIC) :

  Coût de revient C = achat + import (TVA NON récupérable) + port entrant + port sortant
  Bénéfice net à un prix de vente P sur une plateforme :
      profit(P) = P·(1 − commission% − paiement% − urssaf% − impôt% − cfp%) − frais_fixe − C
  Point mort (profit = 0) :
      P_min = (C + frais_fixe) / (1 − commission% − paiement% − urssaf% − impôt% − cfp%)

Assiette URSSAF/impôt = CA BRUT encaissé (commissions plateforme NON déductibles).
Aide à la décision, pas un avis comptable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from bot.config import PricingConfig

# Alias plateforme reconnus dans le salon calculateur (§3.5).
PLATFORM_ALIASES = {
    "ebay": "ebay",
    "cm": "cardmarket",
    "cardmarket": "cardmarket",
    "tiktok": "tiktok",
    "tts": "tiktok",
}
# Marqueurs de devise.
_JPY_TOKENS = ("¥", "yen", "jpy", "jp")
_EUR_TOKENS = ("€", "eur", "euro")


@dataclass
class CalcInput:
    """Résultat du parsing d'un message du salon calculateur."""

    value: float
    currency: str            # 'jpy' | 'eur'
    platform: str | None     # clé plateforme ou None (= comparatif des 3)


def parse_calc_message(text: str) -> CalcInput | None:
    """Parse tolérant : '12000 jpy ebay', '35€ cm', '5000¥', '12,50 eur'.

    Renvoie None si aucun montant exploitable. Devise par défaut : eur si '€' absent
    et aucun token JPY ; sinon déduite des tokens.
    """
    if not text:
        return None
    low = text.lower().strip()

    # montant : premier nombre (gère , et .)
    m = re.search(r"(\d[\d\s.,]*\d|\d)", low.replace("\xa0", " "))
    if not m:
        return None
    raw = m.group(1).replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") \
            else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None

    # devise
    currency = "eur"
    if any(tok in low for tok in _JPY_TOKENS):
        currency = "jpy"
    elif any(tok in low for tok in _EUR_TOKENS):
        currency = "eur"

    # plateforme (premier alias rencontré comme mot)
    platform = None
    for word in re.findall(r"[a-z]+", low):
        if word in PLATFORM_ALIASES:
            platform = PLATFORM_ALIASES[word]
            break

    return CalcInput(value=value, currency=currency, platform=platform)


@dataclass
class CostBreakdown:
    """Coût de revient tout compris (en €)."""

    purchase: float = 0.0
    import_fees: float = 0.0   # TVA import non récupérable + droits éventuels
    shipping_in: float = 0.0
    shipping_out: float = 0.0

    @property
    def total(self) -> float:
        return self.purchase + self.import_fees + self.shipping_in + self.shipping_out


@dataclass
class Tier:
    """Un palier de rentabilité (+X % au-dessus du point mort)."""

    pct_above: float        # 0.0 = point mort, 0.10 = +10 %, …
    sale_price: float
    net_profit: float
    net_margin_pct: float   # bénéfice net / prix de vente


@dataclass
class PlatformResult:
    platform: str
    label: str
    rate_sum: float         # somme des taux ponctionnés (% du prix)
    fixed_fee: float
    p_min: float            # prix de vente de rentabilité minimal (point mort)
    tiers: list[Tier] = field(default_factory=list)


def _platform_rate_sum(platform_cfg: dict, charges: dict) -> float:
    return (
        float(platform_cfg.get("commission_pct", 0.0))
        + float(platform_cfg.get("payment_pct", 0.0))
        + float(charges.get("urssaf_pct", 0.0))
        + float(charges.get("income_tax_pct", 0.0))
        + float(charges.get("cfp_pct", 0.0))
    )


def net_profit(sale_price: float, cost_total: float, rate_sum: float, fixed_fee: float) -> float:
    """Bénéfice net pour un prix de vente donné."""
    return sale_price * (1.0 - rate_sum) - fixed_fee - cost_total


def break_even(cost_total: float, rate_sum: float, fixed_fee: float) -> float:
    """Prix de vente minimal pour un bénéfice net nul."""
    denom = 1.0 - rate_sum
    if denom <= 0:
        raise ValueError(
            f"Somme des taux ({rate_sum:.1%}) ≥ 100 % : aucune rentabilité possible."
        )
    return (cost_total + fixed_fee) / denom


def compute_platform(
    platform_key: str,
    platform_cfg: dict,
    charges: dict,
    cost_total: float,
    tiers_pct: tuple[float, ...] = (0.0, 0.10, 0.20, 0.30),
) -> PlatformResult:
    rate_sum = _platform_rate_sum(platform_cfg, charges)
    fixed_fee = float(platform_cfg.get("fixed_fee_eur", 0.0))
    p_min = break_even(cost_total, rate_sum, fixed_fee)
    tiers: list[Tier] = []
    for pct in tiers_pct:
        price = p_min * (1.0 + pct)
        profit = net_profit(price, cost_total, rate_sum, fixed_fee)
        margin = profit / price if price else 0.0
        tiers.append(Tier(pct_above=pct, sale_price=price, net_profit=profit, net_margin_pct=margin))
    return PlatformResult(
        platform=platform_key,
        label=platform_cfg.get("label", platform_key),
        rate_sum=rate_sum,
        fixed_fee=fixed_fee,
        p_min=p_min,
        tiers=tiers,
    )


def compute_all(
    cost: CostBreakdown,
    config: PricingConfig,
    platforms: list[str] | None = None,
    tiers_pct: tuple[float, ...] = (0.0, 0.10, 0.20, 0.30),
) -> list[PlatformResult]:
    """Calcule le point mort + paliers pour chaque plateforme demandée (toutes par défaut)."""
    charges = config.charges
    all_platforms = config.platforms
    keys = platforms or list(all_platforms.keys())
    results = [
        compute_platform(k, all_platforms[k], charges, cost.total, tiers_pct)
        for k in keys
        if k in all_platforms
    ]
    return results


def cheapest_break_even(results: list[PlatformResult]) -> PlatformResult | None:
    """Plateforme « moins-disante » : celle où il faut vendre le moins cher pour rentabiliser."""
    return min(results, key=lambda r: r.p_min) if results else None
