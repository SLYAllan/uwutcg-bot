"""Radar d'arbitrage Japon → France (§3.6).

/arbitrage watch | list | remove. Polling : coût JP tout compris (services.arbitrage)
vs prix de revente FR de référence (médiane eBay sold §3.2), alerte si marge >= seuil.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.services import arbitrage as arb
from bot.ui import embeds

log = logging.getLogger(__name__)

ARB_POLL_MINUTES = 60


class ArbitrageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="arbitrage", description="Radar d'arbitrage Japon → France")

    @group.command(name="watch", description="Surveille une opportunité d'arbitrage JP→FR")
    @app_commands.describe(query="Terme", min_margin="Marge nette minimale (%) pour alerter")
    async def watch(
        self,
        interaction: discord.Interaction,
        query: str,
        min_margin: float = 30.0,
    ):
        wid = await self.bot.db.execute(
            "INSERT INTO arbitrage_watches(query, min_margin, channel_id) VALUES(?, ?, ?)",
            (query, min_margin / 100.0, interaction.channel.id),
        )
        await interaction.response.send_message(
            f"🛰️ Arbitrage #{wid} sur `{query}` (seuil {min_margin:.0f}%).", ephemeral=True
        )

    @group.command(name="list", description="Liste les surveillances d'arbitrage")
    async def list_(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall("SELECT id, query, min_margin FROM arbitrage_watches ORDER BY id")
        if not rows:
            await interaction.response.send_message("Aucune surveillance.", ephemeral=True)
            return
        lines = [f"**#{r['id']}** `{r['query']}` · seuil {r['min_margin']:.0%}" for r in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Supprime une surveillance d'arbitrage")
    async def remove(self, interaction: discord.Interaction, id: int):
        await self.bot.db.execute("DELETE FROM arbitrage_watches WHERE id = ?", (id,))
        await interaction.response.send_message(f"🗑️ Arbitrage #{id} supprimé.", ephemeral=True)

    # --- polling -------------------------------------------------------------
    @tasks.loop(minutes=ARB_POLL_MINUTES)
    async def poll_loop(self):
        rows = await self.bot.db.fetchall("SELECT * FROM arbitrage_watches")
        for r in rows:
            try:
                await self._check(r)
            except Exception:  # noqa: BLE001
                log.exception("Échec arbitrage #%s", r["id"])

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _check(self, r) -> None:
        jp = await self.bot.japan.cheapest(r["query"])
        if jp is None or jp.price is None:
            return
        # Prix de revente FR de référence : médiane des ventes eBay.
        sold = await self.bot.ebay.search_sold(r["query"])
        resale = sold.median_price
        if resale is None:
            return
        rate = await self.bot.fx.get_rate()
        # Mercari peut afficher déjà en EUR (géo serveur UE) → pas de conversion dans ce cas.
        # analyze() attend un multiplicateur JPY→EUR ; rate.rate est désormais EUR→JPY.
        effective_rate = 1.0 if jp.currency == "EUR" else rate.jpy_to_eur(1.0)
        result = arb.analyze(
            jpy_price=jp.price,
            fx_rate=effective_rate,
            resale_eur=resale,
            config=self.bot.pricing,
            min_margin=r["min_margin"],
        )
        if not result.is_opportunity:
            return
        channel = self.bot.get_channel(int(r["channel_id"]))
        if channel:
            embed = embeds.arbitrage_embed(result, r["query"])
            embed.add_field(name="Annonce Mercari", value=jp.title[:256], inline=False)
            view = self._sourcing_view(jp)
            await channel.send(embed=embed, view=view)

    def _sourcing_view(self, jp) -> discord.ui.View:
        """Boutons lien : commander via FromJapan + voir l'annonce Mercari (§3.10)."""
        view = discord.ui.View(timeout=None)
        fj = jp.extra.get("fromjapan_url")
        if fj:
            view.add_item(
                discord.ui.Button(label="Commander sur FromJapan 🛒", style=discord.ButtonStyle.link, url=fj)
            )
        if jp.url:
            view.add_item(
                discord.ui.Button(label="Voir sur Mercari 🇯🇵", style=discord.ButtonStyle.link, url=jp.url)
            )
        return view


async def setup(bot: commands.Bot):
    await bot.add_cog(ArbitrageCog(bot))
