"""Ventes réussies (§3.2) : /sold platform query → min/médian/max + dernières ventes."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import embeds

log = logging.getLogger(__name__)

PLATFORM_CHOICES = [
    app_commands.Choice(name="eBay", value="ebay"),
    app_commands.Choice(name="Cardmarket", value="cardmarket"),
    app_commands.Choice(name="Vinted", value="vinted"),
]


class SoldCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sold", description="Dernières ventes réussies pour un terme")
    @app_commands.choices(platform=PLATFORM_CHOICES)
    async def sold(
        self,
        interaction: discord.Interaction,
        platform: app_commands.Choice[str],
        query: str,
    ):
        await interaction.response.defer(thinking=True)
        try:
            stats = await self._fetch(platform.value, query)
        except Exception as exc:  # noqa: BLE001
            log.exception("Échec /sold")
            await interaction.followup.send(f"Erreur lors de la récupération : `{exc}`")
            return
        await interaction.followup.send(embed=embeds.sold_embed(stats))

    async def _fetch(self, platform: str, query: str):
        if platform == "ebay":
            return await self.bot.ebay.search_sold(query)
        if platform == "cardmarket":
            return await self.bot.cardmarket.price_trend(query)
        if platform == "vinted":
            # Vinted : pas de filtre "vendu" fiable via l'endpoint public → on renvoie
            # les annonces actives en guise d'approximation, clairement étiquetée.
            from bot.scrapers.base import SoldStats

            items = await self.bot.vinted.search_active(query)
            prices = sorted(i.price for i in items if i.price is not None)
            from statistics import median

            return SoldStats(
                query=query,
                platform="vinted (annonces actives)",
                count=len(items),
                min_price=prices[0] if prices else None,
                median_price=median(prices) if prices else None,
                max_price=prices[-1] if prices else None,
                samples=items[:8],
            )
        raise ValueError(platform)


async def setup(bot: commands.Bot):
    await bot.add_cog(SoldCog(bot))
