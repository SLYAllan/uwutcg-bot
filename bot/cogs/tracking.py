"""Tracking d'annonces multi-plateforme (§3.1).

/track add | list | remove. Polling PAR PLATEFORME au rythme le plus rapide sans risque
de ban (eBay 60 s via API, Vinted 90 s, Cardmarket 300 s via Playwright/Cloudflare),
déduplication via seen_listings, un embed + boutons par nouvelle annonce. Intègre le deal
sniper (§5) et l'anti-arnaque (§5).

Détails clés :
- Boucle « tick » courte : ne lance QUE les recherches dues, en tâches parallèles
  (une recherche lente ne bloque pas les autres). Le rate-limiter par domaine espace déjà
  les requêtes d'une même plateforme.
- Seeding : au 1er passage d'une recherche, les annonces déjà en ligne sont marquées « vues »
  SANS notifier → on n'alerte que sur les vraies nouvelles annonces ensuite.
- Intervalles réglables à chaud via /config set-poll-interval, bornés par un minimum de sécurité.
"""
from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.notify import PING_ALLOWED, add_subscriber, mention_prefix
from bot.scrapers.base import Listing
from bot.scrapers.ebay import build_cart_url
from bot.services.undervalue import looks_like_scam
from bot.ui import embeds
from bot.ui.alerts import build_alert_view

log = logging.getLogger(__name__)

PLATFORM_CHOICES = [
    app_commands.Choice(name="Vinted", value="vinted"),
    app_commands.Choice(name="Cardmarket", value="cardmarket"),
    app_commands.Choice(name="eBay", value="ebay"),
]

# Intervalles de polling par plateforme (secondes) — le plus rapide sans risque de ban.
DEFAULT_INTERVALS = {"ebay": 60, "vinted": 90, "cardmarket": 300}
# Plancher de sécurité : impossible de descendre sous ces valeurs (anti-ban / quota API).
MIN_INTERVALS = {"ebay": 30, "vinted": 60, "cardmarket": 180}
FALLBACK_INTERVAL = 120
TICK_SECONDS = 15  # granularité de la boucle d'ordonnancement


class TrackingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last: dict[int, float] = {}     # search_id -> dernier poll (monotonic)
        self._inflight: set[int] = set()       # recherches en cours (évite le chevauchement)
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="track", description="Suivi d'annonces multi-plateforme")

    # --- commandes -----------------------------------------------------------
    @group.command(name="add", description="Ajoute une recherche à suivre")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @app_commands.describe(
        query="Vinted/eBay : termes de recherche · Cardmarket : nom EXACT de la carte ou URL de sa page",
        channel="Salon de notification (défaut : salon configuré)",
        max_price="Prix maximum en € (recommandé sur Cardmarket pour ne cibler que les deals)",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        query: str,
        channel: discord.TextChannel | None = None,
        max_price: float | None = None,
    ):
        search_id = await self.bot.db.execute(
            "INSERT INTO tracked_searches(platform, query, channel_id, max_price) "
            "VALUES(?, ?, ?, ?)",
            (platform.value, query, channel.id if channel else None, max_price),
        )
        await add_subscriber(self.bot.db, interaction.user.id)  # le créateur est pingué
        await interaction.response.send_message(
            f"✅ Suivi **#{search_id}** — {platform.name} : `{query}`"
            + (f" (≤ {max_price:.2f} €)" if max_price else ""),
            ephemeral=True,
        )

    @group.command(name="list", description="Liste les recherches suivies")
    async def list_(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall(
            "SELECT id, platform, query, max_price, muted FROM tracked_searches ORDER BY id"
        )
        if not rows:
            await interaction.response.send_message("Aucune recherche suivie.", ephemeral=True)
            return
        lines = [
            f"**#{r['id']}** {r['platform']} · `{r['query']}`"
            + (f" ≤{r['max_price']:.0f}€" if r["max_price"] else "")
            + (" 🔕" if r["muted"] else "")
            for r in rows
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Supprime une recherche suivie")
    async def remove(self, interaction: discord.Interaction, id: int):
        await self.bot.db.execute("DELETE FROM tracked_searches WHERE id = ?", (id,))
        await interaction.response.send_message(f"🗑️ Suivi #{id} supprimé.", ephemeral=True)

    # --- polling -------------------------------------------------------------
    async def _intervals(self) -> dict[str, int]:
        """Intervalles effectifs (défauts + overrides config), bornés au minimum de sécurité."""
        overrides = await self.bot.db.config_get("poll_intervals", default={}) or {}
        merged = {**DEFAULT_INTERVALS, **overrides}
        return {p: max(int(v), MIN_INTERVALS.get(p, 30)) for p, v in merged.items()}

    @tasks.loop(seconds=TICK_SECONDS)
    async def poll_loop(self):
        """Ordonnanceur : lance uniquement les recherches dues, en parallèle."""
        intervals = await self._intervals()
        rows = await self.bot.db.fetchall(
            "SELECT id, platform, query, channel_id, max_price FROM tracked_searches "
            "WHERE muted = 0"
        )
        now = time.monotonic()
        for r in rows:
            sid = r["id"]
            if sid in self._inflight:
                continue
            interval = intervals.get(r["platform"], FALLBACK_INTERVAL)
            if now - self._last.get(sid, 0.0) < interval:
                continue
            self._last[sid] = now
            self._inflight.add(sid)
            asyncio.create_task(self._poll_wrap(r))

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _poll_wrap(self, r) -> None:
        try:
            await self._poll_one(r)
        except Exception:  # noqa: BLE001 - une recherche ne doit pas tuer la boucle
            log.exception("Échec polling recherche #%s", r["id"])
        finally:
            self._inflight.discard(r["id"])

    async def _poll_one(self, r) -> None:
        listings = await self._search(r["platform"], r["query"], r["max_price"])
        # Seeding : au 1er passage, on marque tout comme vu SANS notifier (pas de flood).
        already = await self.bot.db.fetchone(
            "SELECT COUNT(*) AS c FROM seen_listings WHERE search_id = ?", (r["id"],)
        )
        seeding = (already["c"] == 0) if already else False
        channel = None if seeding else await self._resolve_channel(r["channel_id"])
        for listing in listings:
            if await self.bot.db.is_seen(r["id"], listing.key):
                continue
            seen_id = await self.bot.db.mark_seen(r["id"], listing.key)
            if seeding or channel is None:
                continue
            await self._notify(channel, r, listing, seen_id)

    async def _search(self, platform: str, query: str, max_price) -> list[Listing]:
        if platform == "ebay":
            return await self.bot.ebay.search_active(query, max_price=max_price)
        if platform == "vinted":
            return await self.bot.vinted.search_active(query, max_price=max_price)
        if platform == "cardmarket":
            # CM = catalogue : on suit les OFFRES d'une carte précise (nom exact ou URL),
            # dédup par ID d'offre, filtrées par prix max → deal sniper.
            return await self.bot.cardmarket.card_offers(query, max_price=max_price)
        return []

    async def _notify(self, channel, r, listing: Listing, seen_id: int) -> None:
        deal_note = None
        # Deal sniper / anti-arnaque : si max_price défini, on l'utilise comme proxy marché
        if r["max_price"] and listing.price is not None:
            if looks_like_scam(listing.price, r["max_price"]):
                deal_note = "⚠️ Prix anormalement bas — vérifier (possible arnaque)."
            elif listing.price <= r["max_price"]:
                pct = (r["max_price"] - listing.price) / r["max_price"]
                if pct >= 0.10:
                    deal_note = f"{pct:.0%} sous ton prix max."
        link_url = self._link_for(listing)
        embed = embeds.listing_embed(listing, deal_note=deal_note)
        view = build_alert_view(
            link_url=link_url,
            seen_id=seen_id,
            price=listing.price,
            is_ebay=(listing.platform == "ebay"),
        )
        mentions = await mention_prefix(self.bot.db)
        await channel.send(content=mentions, embed=embed, view=view, allowed_mentions=PING_ALLOWED)

    def _link_for(self, listing: Listing) -> str | None:
        if listing.platform == "ebay" and listing.item_id:
            if "FIXED_PRICE" in (listing.extra.get("buyingOptions") or []):
                return build_cart_url(listing.item_id)
            return listing.url
        if listing.platform == "vinted" and listing.item_id:
            return self.bot.vinted.item_url(listing.item_id)
        return listing.url or None

    async def _resolve_channel(self, channel_id):
        cid = channel_id
        if cid is None:
            cid = await self.bot.db.config_get("default_track_channel_id")
        if cid is None:
            cid = self.bot.settings.default_track_channel_id
        if cid is None:
            return None
        return self.bot.get_channel(int(cid))


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackingCog(bot))
