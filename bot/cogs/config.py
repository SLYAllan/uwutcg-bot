"""Cog de configuration à chaud (table `config`) — §1 réglage en jeu.

Permet de régler les salons par défaut et de visualiser/éditer les taux du calculateur.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class ConfigCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="config", description="Configuration du bot")

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
