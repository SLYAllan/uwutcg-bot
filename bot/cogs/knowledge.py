"""Consultation de la base de connaissances locale (§2).

/riftbound, /pokemon, /condition, /grading lisent les .md de knowledge/ via recherche
fuzzy par section (services.knowledge). Le bot N'UTILISE PAS l'API Claude.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

MAX_LEN = 1800


class KnowledgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _answer(self, doc: str, term: str, title_prefix: str) -> discord.Embed:
        sections = self.bot.knowledge.search(doc, term, limit=2)
        if not sections:
            titles = self.bot.knowledge.list_section_titles(doc)
            hint = ", ".join(titles[:12]) if titles else "(doc vide)"
            return discord.Embed(
                title=f"{title_prefix} — rien pour « {term} »",
                description=f"Sections disponibles : {hint}",
                color=0xE67E22,
            )
        main = sections[0]
        body = main.body[:MAX_LEN] + ("…" if len(main.body) > MAX_LEN else "")
        e = discord.Embed(title=f"{title_prefix} — {main.title}", description=body, color=0x5865F2)
        if len(sections) > 1:
            e.set_footer(text=f"Voir aussi : {sections[1].title}")
        return e

    @app_commands.command(name="riftbound", description="Recherche dans la base Riftbound")
    async def riftbound(self, interaction: discord.Interaction, terme: str):
        await interaction.response.send_message(embed=self._answer("riftbound", terme, "Riftbound"))

    @app_commands.command(name="pokemon", description="Recherche dans la base Pokémon")
    async def pokemon(self, interaction: discord.Interaction, terme: str):
        await interaction.response.send_message(embed=self._answer("pokemon", terme, "Pokémon"))

    @app_commands.command(name="condition", description="Explique un état de carte (Cardmarket)")
    async def condition(self, interaction: discord.Interaction, etat: str):
        await interaction.response.send_message(
            embed=self._answer("card_conditions", etat, "Condition")
        )

    @app_commands.command(name="grading", description="Explique une échelle de grading")
    async def grading(self, interaction: discord.Interaction, societe: str):
        await interaction.response.send_message(embed=self._answer("grading", societe, "Grading"))


async def setup(bot: commands.Bot):
    await bot.add_cog(KnowledgeCog(bot))
