"""Estimateur de ROI de grading (§3.7) : /grading-roi.

Récupère le prix raw (médiane eBay sold de la carte) et les prix gradés (médiane eBay
sold "<carte> <société> <note>"), déduit les coûts de grading (services.grading_roi),
et sort la plus-value nette + le point mort par note.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.services import grading_roi
from bot.ui import embeds

log = logging.getLogger(__name__)

COMPANY_CHOICES = [
    app_commands.Choice(name="PSA", value="psa"),
    app_commands.Choice(name="CGC", value="cgc"),
    app_commands.Choice(name="BGS", value="bgs"),
    app_commands.Choice(name="PCA", value="pca"),
]
DEFAULT_GRADES = ["10", "9.5", "9"]


class GradingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="grading-roi", description="Estime le ROI d'un grading")
    @app_commands.choices(company=COMPANY_CHOICES)
    @app_commands.describe(card="Nom ou URL de la carte", grade="Note visée (optionnel)")
    async def grading_roi_cmd(
        self,
        interaction: discord.Interaction,
        card: str,
        company: app_commands.Choice[str],
        grade: str | None = None,
    ):
        await interaction.response.defer(thinking=True)
        raw_stats = await self.bot.ebay.search_sold(card)
        raw_price = raw_stats.median_price
        if raw_price is None:
            await interaction.followup.send("Pas de prix raw trouvé (ventes eBay).")
            return

        grades = [grade] if grade else DEFAULT_GRADES
        graded_prices: dict[str, float] = {}
        for g in grades:
            stats = await self.bot.ebay.search_sold(f"{card} {company.value} {g}")
            if stats.median_price is not None:
                graded_prices[f"{company.name} {g}"] = stats.median_price
        if not graded_prices:
            await interaction.followup.send("Pas de prix gradé trouvé pour ces notes.")
            return

        roi = grading_roi.estimate(company.value, raw_price, graded_prices, self.bot.pricing)
        await interaction.followup.send(embed=embeds.grading_embed(roi, card))


async def setup(bot: commands.Bot):
    await bot.add_cog(GradingCog(bot))
