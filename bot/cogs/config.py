"""Cog de configuration à chaud (table `config`) — §1 réglage en jeu.

Permet de régler les salons par défaut et de visualiser/éditer les taux du calculateur.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.tracking import DEFAULT_INTERVALS, MIN_INTERVALS

INTERVAL_PLATFORMS = [
    app_commands.Choice(name="eBay", value="ebay"),
    app_commands.Choice(name="Vinted", value="vinted"),
    app_commands.Choice(name="Cardmarket", value="cardmarket"),
]


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="config", description="Configuration du bot")

    @group.command(name="set-poll-interval", description="Règle la fréquence de polling d'une plateforme")
    @app_commands.choices(platform=INTERVAL_PLATFORMS)
    @app_commands.describe(seconds="Intervalle en secondes (borné au minimum de sécurité)")
    async def set_poll_interval(
        self, interaction: discord.Interaction, platform: app_commands.Choice[str], seconds: int
    ):
        floor = MIN_INTERVALS.get(platform.value, 30)
        applied = max(seconds, floor)
        current = await self.bot.db.config_get("poll_intervals", default={}) or {}
        current[platform.value] = applied
        await self.bot.db.config_set("poll_intervals", current)
        note = "" if applied == seconds else f" (borné au minimum sécurité {floor}s)"
        await interaction.response.send_message(
            f"⏱️ {platform.name} : polling toutes les **{applied}s**{note}.", ephemeral=True
        )

    @group.command(name="poll-intervals", description="Affiche les fréquences de polling")
    async def poll_intervals(self, interaction: discord.Interaction):
        overrides = await self.bot.db.config_get("poll_intervals", default={}) or {}
        lines = []
        for p, default in DEFAULT_INTERVALS.items():
            val = max(int(overrides.get(p, default)), MIN_INTERVALS.get(p, 30))
            tag = "" if p in overrides else " (défaut)"
            lines.append(f"**{p}** : {val}s{tag} · min {MIN_INTERVALS.get(p, 30)}s")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="set-default-channel", description="Définit le salon de tracking par défaut")
    async def set_default_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await self.bot.db.config_set("default_track_channel_id", channel.id)
        await interaction.response.send_message(
            f"Salon de tracking par défaut → {channel.mention}", ephemeral=True
        )

    @group.command(name="set-digest-channel", description="Définit le salon du digest quotidien")
    async def set_digest_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await self.bot.db.config_set("daily_digest_channel_id", channel.id)
        await interaction.response.send_message(
            f"Salon digest quotidien → {channel.mention}", ephemeral=True
        )

    @group.command(name="show", description="Affiche la configuration courante")
    async def show(self, interaction: discord.Interaction):
        cfg = await self.bot.db.config_all()
        lines = [f"`{k}` = `{v}`" for k, v in cfg.items()] or ["(vide)"]
        embed = discord.Embed(
            title="⚙️ Configuration", description="\n".join(lines), color=0x5865F2
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ConfigCog(bot))
