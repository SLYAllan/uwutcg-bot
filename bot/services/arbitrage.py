"""Radar d'arbitrage Japon → France (§3.6). Logique pure → testée.

Entrées : prix de sourcing JP (en JPY), taux FX, prix de revente FR de référence (€).
Sortie : coût d'achat tout compris en € + marge nette estimée par plateforme de revente,
et drapeau d'opportunité si la meilleure marge dépasse le seuil configuré.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bot.config import PricingConfig
from bot.services.pricing import net_profit, _platform_rate_sum


@dataclass
class JapanCost:
    """Décomposition du coût d'achat JP tout compris (en €)."""

    base_eur: float
    proxy_commission: float
    proxy_fixed: float
    intl_shipping: float
    import_vat: float

    @property
    def total(self) -> float:
        return (
            self.base_eur
            + self.proxy_commission
            + self.proxy_fixed
            + self.intl_shipping
            + self.import_vat
        )


@dataclass
class PlatformMargin:
    platform: str
    label: str
    net_profit: float
    net_margin_pct: float


@dataclass
class ArbitrageResult:
    jpy_price: float
    fx_rate: float
    cost: JapanCost
    resale_eur: float
    margins: list[PlatformMargin] = field(default_factory=list)
    min_margin_threshold: float = 0.30

    @property
    def best(self) -> PlatformMargin | None:
        return max(self.margins, key=lambda m: m.net_margin_pct) if self.margins else None

    @property
    def is_opportunity(self) -> bool:
        b = self.best
        return b is not None and b.net_margin_pct >= self.min_margin_threshold


def japan_all_in_cost(jpy_price: float, fx_rate: float, config: PricingConfig) -> JapanCost:
    """Coût d'achat JP converti et tout compris (commission proxy, port, TVA import)."""
    s = config.sourcing
    base = jpy_price * fx_rate
    proxy_commission = base * float(s.get("proxy_commission_pct", 0.0))
    proxy_fixed = float(s.get("proxy_fixed_fee_eur", 0.0))
    intl = float(s.get("intl_shipping_eur", 0.0))
    pre_vat = base + proxy_commission + proxy_fixed + intl
    threshold = float(s.get("customs_threshold_eur", 0.0))
    vat = pre_vat * float(s.get("import_vat_pct", 0.0)) if pre_vat >= threshold else 0.0
    return JapanCost(
        base_eur=base,
        proxy_commission=proxy_commission,
        proxy_fixed=proxy_fixed,
        intl_shipping=intl,
        import_vat=vat,
    )


def analyze(
    jpy_price: float,
    fx_rate: float,
    resale_eur: float,
    config: PricingConfig,
    platforms: list[str] | None = None,
    min_margin: float | None = None,
) -> ArbitrageResult:
    cost = japan_all_in_cost(jpy_price, fx_rate, config)
    charges = config.charges
    keys = platforms or list(config.platforms.keys())
    margins: list[PlatformMargin] = []
    for key in keys:
        pcfg = config.platforms.get(key)
        if not pcfg:
            continue
        rate_sum = _platform_rate_sum(pcfg, charges)
        fixed = float(pcfg.get("fixed_fee_eur", 0.0))
        profit = net_profit(resale_eur, cost.total, rate_sum, fixed)
        margin = profit / resale_eur if resale_eur else 0.0
        margins.append(
            PlatformMargin(
                platform=key,
                label=pcfg.get("label", key),
                net_profit=profit,
                net_margin_pct=margin,
            )
        )
    threshold = (
        min_margin
        if min_margin is not None
        else float(config.thresholds.get("arbitrage_min_margin_pct", 0.30))
    )
    return ArbitrageResult(
        jpy_price=jpy_price,
        fx_rate=fx_rate,
        cost=cost,
        resale_eur=resale_eur,
        margins=margins,
        min_margin_threshold=threshold,
    )
