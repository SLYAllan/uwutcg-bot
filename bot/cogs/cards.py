"""Lookup de cartes Riftbound (§extension) : /carte <nom>.

Charge la base via l'API Riftcodex (cache mémoire), recherche fuzzy par nom, et affiche
un embed (image, domaines, type, stats, rareté, collector) + le prix Cardmarket EUR mini
(best effort). Si plusieurs cartes correspondent, propose les alternatives en pied.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.ui import embeds

log = logging.getLogger(__name__)


class CardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="carte", description="Recherche une carte Riftbound (Riftcodex)")
    @app_commands.describe(nom="Nom de la carte", prix="Inclure le prix Cardmarket (plus lent)")
    async def carte(self, interaction: discord.Interaction, nom: str, prix: bool = False):
        await interaction.response.defer(thinking=True)
        try:
            results = await self.bot.riftcodex.search(nom, limit=5)
        except Exception as exc:  # noqa: BLE001
            log.exception("Échec recherche Riftcodex")
            await interaction.followup.send(f"Base de cartes indisponible : `{exc}`")
            return
        if not results:
            await interaction.followup.send(f"Aucune carte ne correspond à « {nom} ».")
            return
        card = results[0]

        cm_price = None
        if prix:
            try:
                cm_price = await self.bot.cardmarket.lowest_price(card.name, game="riftbound")
            except Exception:  # noqa: BLE001 - le prix ne doit pas bloquer la réponse
                log.warning("Prix Cardmarket indisponible pour %s", card.name)

        embed = embeds.card_embed(card, cm_price=cm_price)
        if len(results) > 1:
            others = " · ".join(c.name for c in results[1:])
            embed.add_field(name="Autres résultats", value=others[:1024], inline=False)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CardsCog(bot))
