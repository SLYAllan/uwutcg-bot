"""Estimateur de ROI de grading (§3.7). Logique pure → testée.

Compare le prix raw actuel au prix gradé (par société et par note), déduit les coûts
de grading (tarif + port A/R + assurance) et sort la plus-value nette + le point mort
(à partir de quelle note ça devient rentable).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bot.config import PricingConfig


@dataclass
class GradeOutcome:
    grade: str               # ex. "10", "9.5", "PSA 10"
    graded_price: float
    net_gain: float          # plus-value nette après coûts
    roi_pct: float           # net_gain / coût total (raw + grading)


@dataclass
class GradingRoi:
    company: str
    raw_price: float
    grading_cost: float      # tarif + port + assurance
    outcomes: list[GradeOutcome] = field(default_factory=list)

    @property
    def break_even_grade(self) -> str | None:
        """Plus basse note (ordre croissant) où la plus-value nette devient positive."""
        positives = [o for o in self.outcomes if o.net_gain >= 0]
        return positives[0].grade if positives else None


def grading_cost(company: str, config: PricingConfig) -> float:
    g = config.grading.get(company.lower(), {})
    return (
        float(g.get("fee_eur", 0.0))
        + float(g.get("shipping_eur", 0.0))
        + float(g.get("insurance_eur", 0.0))
    )


def estimate(
    company: str,
    raw_price: float,
    graded_prices: dict[str, float],
    config: PricingConfig,
) -> GradingRoi:
    """`graded_prices` : {note -> prix de vente gradé observé}. Triés par note croissante."""
    cost = grading_cost(company, config)
    total_invest = raw_price + cost
    outcomes: list[GradeOutcome] = []
    for grade in _sorted_grades(graded_prices):
        gp = graded_prices[grade]
        net = gp - raw_price - cost
        roi = net / total_invest if total_invest else 0.0
        outcomes.append(GradeOutcome(grade=grade, graded_price=gp, net_gain=net, roi_pct=roi))
    return GradingRoi(company=company, raw_price=raw_price, grading_cost=cost, outcomes=outcomes)


def _sorted_grades(grades: dict[str, float]) -> list[str]:
    """Tri par valeur numérique de la note quand possible (sinon ordre alpha)."""
    def key(g: str):
        import re

        m = re.search(r"(\d+(?:\.\d+)?)", g)
        return (0, float(m.group(1))) if m else (1, g)

    return sorted(grades.keys(), key=key)
