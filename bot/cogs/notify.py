"""Abonnés aux notifications : qui le bot mentionne (ping) sur les alertes.

Liste globale stockée dans la table config (`notify_user_ids`). S'applique aux alertes
de tracking (§3.1), aux mises à jour de monitoring (§3.4) et au digest quotidien (§3.3).
- Le créateur d'un /track ou /monitor est ajouté automatiquement (add_subscriber).
- /notify on|off (soi-même) · /notify add|remove user:@X · /notify list.

Opt-in : tant que la liste est vide, le bot ne ping personne (juste l'embed).
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

NOTIFY_KEY = "notify_user_ids"
# Autorise explicitement les mentions d'utilisateurs (et rien d'autre → pas de @everyone).
PING_ALLOWED = discord.AllowedMentions(users=True, everyone=False, roles=False)


async def get_subscribers(db) -> list[int]:
    return [int(x) for x in (await db.config_get(NOTIFY_KEY, default=[]) or [])]


async def add_subscriber(db, user_id: int) -> bool:
    """Ajoute un abonné. Renvoie True s'il a été ajouté, False s'il y était déjà."""
    subs = await get_subscribers(db)
    if user_id in subs:
        return False
    subs.append(user_id)
    await db.config_set(NOTIFY_KEY, subs)
    return True


async def remove_subscriber(db, user_id: int) -> bool:
    subs = await get_subscribers(db)
    if user_id not in subs:
        return False
    subs = [u for u in subs if u != user_id]
    await db.config_set(NOTIFY_KEY, subs)
    return True


async def mention_prefix(db) -> str | None:
    """Chaîne de mentions à mettre en tête d'une alerte, ou None si personne abonné."""
    subs = await get_subscribers(db)
    return " ".join(f"<@{u}>" for u in subs) if subs else None


class NotifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    group = app_commands.Group(name="notify", description="Qui le bot ping sur les alertes")

    @group.command(name="on", description="M'ajouter aux personnes pinguées sur les alertes")
    async def on(self, interaction: discord.Interaction):
        added = await add_subscriber(self.bot.db, interaction.user.id)
        msg = "🔔 Tu seras pingué sur les alertes." if added else "Tu étais déjà abonné."
        await interaction.response.send_message(msg, ephemeral=True)

    @group.command(name="off", description="Ne plus me pinguer sur les alertes")
    async def off(self, interaction: discord.Interaction):
        removed = await remove_subscriber(self.bot.db, interaction.user.id)
        msg = "🔕 Tu ne seras plus pingué." if removed else "Tu n'étais pas abonné."
        await interaction.response.send_message(msg, ephemeral=True)

    @group.command(name="add", description="Ajouter quelqu'un aux personnes pinguées")
    async def add(self, interaction: discord.Interaction, user: discord.User):
        added = await add_subscriber(self.bot.db, user.id)
        msg = f"🔔 {user.mention} sera pingué sur les alertes." if added else f"{user.mention} était déjà abonné."
        await interaction.response.send_message(msg, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @group.command(name="remove", description="Retirer quelqu'un des personnes pinguées")
    async def remove(self, interaction: discord.Interaction, user: discord.User):
        removed = await remove_subscriber(self.bot.db, user.id)
        msg = f"🔕 {user.mention} ne sera plus pingué." if removed else f"{user.mention} n'était pas abonné."
        await interaction.response.send_message(msg, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @group.command(name="list", description="Voir qui est pingué sur les alertes")
    async def list_(self, interaction: discord.Interaction):
        subs = await get_subscribers(self.bot.db)
        if not subs:
            await interaction.response.send_message(
                "Personne n'est abonné (aucun ping). Fais `/notify on` pour t'ajouter.",
                ephemeral=True,
            )
            return
        who = ", ".join(f"<@{u}>" for u in subs)
        await interaction.response.send_message(
            f"🔔 Pingés sur les alertes : {who}",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotifyCog(bot))
