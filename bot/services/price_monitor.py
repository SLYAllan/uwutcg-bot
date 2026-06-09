"""Monitoring de prix : tendances + graphique (§3.4, §3.8).

- `trend_pct` : variation entre le 1er et le dernier point d'une fenêtre (pur → testé).
- `build_price_chart` : rend un PNG (matplotlib, backend Agg) à poster dans un embed.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")  # pas d'affichage : on génère des PNG côté serveur
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


def trend_pct(prices: list[float]) -> float | None:
    """Variation relative entre le premier et le dernier point. None si < 2 points."""
    if len(prices) < 2 or prices[0] == 0:
        return None
    return (prices[-1] - prices[0]) / prices[0]


def window_prices(rows: list[dict], days: int) -> list[float]:
    """Filtre les prix dans les `days` derniers jours à partir de rows {price, recorded_at}."""
    from datetime import timedelta

    cutoff = _utcnow_naive() - timedelta(days=days)
    out: list[float] = []
    for r in rows:
        ts = _parse_ts(r["recorded_at"])
        if ts is None or ts >= cutoff:
            out.append(float(r["price"]))
    return out


def _utcnow_naive() -> datetime:
    """UTC sans tzinfo : cohérent avec les timestamps SQLite (datetime('now') = UTC naïf)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_ts(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


def build_price_chart(rows: list[dict], title: str) -> bytes:
    """Construit un graphique d'historique de prix et renvoie les octets PNG."""
    times = [_parse_ts(r["recorded_at"]) or _utcnow_naive() for r in rows]
    prices = [float(r["price"]) for r in rows]

    fig, ax = plt.subplots(figsize=(8, 3.5), dpi=110)
    ax.plot(times, prices, marker="o", markersize=3, linewidth=1.6, color="#5865F2")
    ax.fill_between(times, prices, min(prices) if prices else 0, alpha=0.12, color="#5865F2")
    ax.set_title(title, fontsize=11)
    ax.set_ylabel("Prix (€)")
    ax.grid(True, alpha=0.25)
    if times:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        fig.autofmt_xdate(rotation=30)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()
