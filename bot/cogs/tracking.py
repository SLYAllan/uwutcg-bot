"""Tracking d'annonces multi-plateforme (§3.1).

/track add | list | remove. Polling périodique (défaut 7 min), déduplication via
seen_listings, un embed + boutons d'action par nouvelle annonce. Intègre le deal sniper
(§5) et l'heuristique anti-arnaque (§5) via services.undervalue.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

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
POLL_MINUTES = 7


class TrackingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="track", description="Suivi d'annonces multi-plateforme")

    # --- commandes -----------------------------------------------------------
    @group.command(name="add", description="Ajoute une recherche à suivre")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    @app_commands.describe(
        query="Terme de recherche",
        channel="Salon de notification (défaut : salon configuré)",
        max_price="Prix maximum en €",
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
    @tasks.loop(minutes=POLL_MINUTES)
    async def poll_loop(self):
        rows = await self.bot.db.fetchall(
            "SELECT id, platform, query, channel_id, max_price FROM tracked_searches "
            "WHERE muted = 0"
        )
        for r in rows:
            try:
                await self._poll_one(r)
            except Exception:  # noqa: BLE001 - une recherche ne doit pas tuer la boucle
                log.exception("Échec polling recherche #%s", r["id"])

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _poll_one(self, r) -> None:
        listings = await self._search(r["platform"], r["query"], r["max_price"])
        channel = await self._resolve_channel(r["channel_id"])
        if channel is None:
            return
        for listing in listings:
            if await self.bot.db.is_seen(r["id"], listing.key):
                continue
            seen_id = await self.bot.db.mark_seen(r["id"], listing.key)
            await self._notify(channel, r, listing, seen_id)

    async def _search(self, platform: str, query: str, max_price) -> list[Listing]:
        if platform == "ebay":
            return await self.bot.ebay.search_active(query, max_price=max_price)
        if platform == "vinted":
            return await self.bot.vinted.search_active(query, max_price=max_price)
        if platform == "cardmarket":
            return await self.bot.cardmarket.search(query)
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
        await channel.send(embed=embed, view=view)

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
