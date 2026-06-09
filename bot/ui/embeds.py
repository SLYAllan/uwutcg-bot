"""Constructeurs d'embeds Discord. Aucune logique métier : juste de la mise en forme."""
from __future__ import annotations

import discord

from bot.scrapers.base import Listing, SoldStats
from bot.services.arbitrage import ArbitrageResult
from bot.services.grading_roi import GradingRoi
from bot.services.pricing import PlatformResult

PLATFORM_COLORS = {
    "vinted": 0x09B1BA,
    "cardmarket": 0xFFC107,
    "ebay": 0xE53238,
    "japan:mercari": 0xFF0211,
    "japan:yahoo": 0xFF0033,
}


def listing_embed(listing: Listing, *, deal_note: str | None = None) -> discord.Embed:
    color = PLATFORM_COLORS.get(listing.platform, 0x5865F2)
    e = discord.Embed(title=listing.title[:256], url=listing.url or None, color=color)
    if listing.price is not None:
        e.add_field(name="Prix", value=f"{listing.price:.2f} {listing.currency}", inline=True)
    e.add_field(name="Plateforme", value=listing.platform, inline=True)
    if listing.condition:
        e.add_field(name="État", value=str(listing.condition), inline=True)
    if listing.seller:
        e.add_field(name="Vendeur", value=str(listing.seller), inline=True)
    if listing.image_url:
        e.set_thumbnail(url=listing.image_url)
    if deal_note:
        e.add_field(name="🔥 Deal", value=deal_note, inline=False)
    return e


def sold_embed(stats: SoldStats) -> discord.Embed:
    e = discord.Embed(
        title=f"Ventes réussies — {stats.query}",
        description=f"Plateforme : **{stats.platform}** · {stats.count} ventes trouvées",
        color=0x2ECC71,
    )
    if stats.median_price is not None:
        e.add_field(name="Min", value=f"{stats.min_price:.2f} €", inline=True)
        e.add_field(name="Médian", value=f"{stats.median_price:.2f} €", inline=True)
        e.add_field(name="Max", value=f"{stats.max_price:.2f} €", inline=True)
    for s in stats.samples[:8]:
        price = f"{s.price:.2f} €" if s.price is not None else "?"
        e.add_field(name=price, value=(s.title[:60] or "—"), inline=False)
    return e


def calc_embed(
    results: list[PlatformResult], cheapest_key: str | None, *, header: str
) -> discord.Embed:
    e = discord.Embed(title="🧮 Seuil de rentabilité", description=header, color=0x5865F2)
    for r in results:
        crown = " 👑" if r.platform == cheapest_key else ""
        lines = [f"**Point mort : {r.p_min:.2f} €**{crown}"]
        for t in r.tiers:
            if t.pct_above == 0:
                continue
            lines.append(
                f"+{t.pct_above*100:.0f}% → {t.sale_price:.2f} € "
                f"(net {t.net_profit:+.2f} €, marge {t.net_margin_pct:.0%})"
            )
        lines.append(f"_ponctions {r.rate_sum:.1%} + {r.fixed_fee:.2f} € fixe_")
        e.add_field(name=r.label, value="\n".join(lines), inline=False)
    return e


def arbitrage_embed(res: ArbitrageResult, query: str) -> discord.Embed:
    color = 0x2ECC71 if res.is_opportunity else 0x95A5A6
    e = discord.Embed(
        title=f"{'🟢 OPPORTUNITÉ' if res.is_opportunity else '🔎 Arbitrage'} — {query}",
        color=color,
    )
    c = res.cost
    e.add_field(
        name="Coût JP tout compris",
        value=(
            f"Base {c.base_eur:.2f} € · proxy {c.proxy_commission + c.proxy_fixed:.2f} € · "
            f"port {c.intl_shipping:.2f} € · TVA import {c.import_vat:.2f} €\n"
            f"**Total {c.total:.2f} €** (≈ {res.jpy_price:.0f} JPY @ {res.fx_rate:.5f})"
        ),
        inline=False,
    )
    e.add_field(name="Revente FR de réf.", value=f"{res.resale_eur:.2f} €", inline=True)
    for m in res.margins:
        e.add_field(
            name=m.label,
            value=f"net {m.net_profit:+.2f} € · marge {m.net_margin_pct:.0%}",
            inline=True,
        )
    return e


def grading_embed(roi: GradingRoi, card: str) -> discord.Embed:
    e = discord.Embed(
        title=f"🏅 ROI grading {roi.company.upper()} — {card}",
        description=(
            f"Raw {roi.raw_price:.2f} € · coût grading {roi.grading_cost:.2f} € · "
            f"point mort à partir de la note **{roi.break_even_grade or 'aucune'}**"
        ),
        color=0xF1C40F,
    )
    for o in roi.outcomes:
        e.add_field(
            name=f"Note {o.grade} → {o.graded_price:.2f} €",
            value=f"plus-value nette {o.net_gain:+.2f} € (ROI {o.roi_pct:+.0%})",
            inline=False,
        )
    return e
