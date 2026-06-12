"""Constructeurs d'embeds Discord. Aucune logique métier : juste de la mise en forme."""
from __future__ import annotations

import discord

from bot.scrapers.base import Listing, SoldStats
from bot.scrapers.riftcodex import Card
from bot.services.arbitrage import ArbitrageResult
from bot.services.grading_roi import GradingRoi
from bot.services.pricing import PlatformResult

PLATFORM_COLORS = {
    "vinted": 0x09B1BA,
    "cardmarket": 0xFFC107,
    "ebay": 0xE53238,
    "mercari": 0xFF0211,
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
        e.set_image(url=listing.image_url)  # image pleine largeur (plus lisible qu'une vignette)
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
            f"**Total {c.total:.2f} €** (≈ {res.jpy_price:.0f} JPY @ 1 € = "
            f"{1 / res.fx_rate if res.fx_rate else 0:.2f} JPY)"
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


DOMAIN_COLORS = {
    "Fury": 0xE74C3C, "Furie": 0xE74C3C,
    "Calm": 0x2ECC71, "Calme": 0x2ECC71,
    "Mind": 0x3498DB, "Esprit": 0x3498DB,
    "Body": 0xE67E22, "Corps": 0xE67E22,
    "Chaos": 0x9B59B6,
    "Order": 0xF1C40F, "Ordre": 0xF1C40F,
}


def card_embed(card: Card, *, cm_price: float | None = None) -> discord.Embed:
    """Embed d'une carte Riftbound (données Riftcodex) + prix Cardmarket optionnel."""
    color = DOMAIN_COLORS.get(card.domains[0], 0x5865F2) if card.domains else 0x5865F2
    title = card.name
    if card.collector_number:
        title += f"  ·  {card.collector_number}"
    e = discord.Embed(title=title, description=card.text_plain[:1024] or None, color=color)
    if card.domains:
        e.add_field(name="Domaine(s)", value=" / ".join(card.domains), inline=True)
    type_line = " ".join(x for x in [card.supertype, card.type] if x) or "—"
    e.add_field(name="Type", value=type_line, inline=True)
    if card.rarity:
        e.add_field(name="Rareté", value=card.rarity, inline=True)
    # Stats (les Legends ont attributes=null)
    if not card.is_legend:
        stats = []
        if card.energy is not None:
            stats.append(f"⚡ Énergie {card.energy}")
        if card.might is not None:
            stats.append(f"💪 Puissance {card.might}")
        if card.power is not None:
            stats.append(f"🔋 Power {card.power}")
        if stats:
            e.add_field(name="Stats", value=" · ".join(stats), inline=False)
    flags = [
        x for x, on in [
            ("alt art", card.alternate_art),
            ("overnumbered", card.overnumbered),
            ("signature", card.signature),
        ] if on
    ]
    if flags:
        e.add_field(name="Collector", value=", ".join(flags), inline=True)
    if cm_price is not None:
        e.add_field(name="💶 Cardmarket (mini)", value=f"{cm_price:.2f} €", inline=True)
    if card.set_label:
        e.set_footer(text=f"{card.set_label}" + (f" · ill. {card.artist}" if card.artist else ""))
    if card.image_url:
        e.set_image(url=card.image_url)
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
