"""Monitoring de prix détaillé d'une carte Cardmarket (§3.4).

/monitor create → crée un salon dédié et y publie un suivi détaillé mis à jour
périodiquement (prix mini, nb offres, répartition état/langue, gradées vs raw,
historique construit par le bot, tendances 7j/30j, graphique).
"""
from __future__ import annotations

import io
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.services.price_monitor import build_price_chart, trend_pct, window_prices

log = logging.getLogger(__name__)

MONITOR_POLL_MINUTES = 180  # 3 h : Cardmarket via Playwright, on espace les hits


class MonitorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="monitor", description="Suivi détaillé d'une carte Cardmarket")

    @group.command(name="create", description="Crée un salon de suivi pour une carte")
    @app_commands.describe(card="Nom de la carte ou URL Cardmarket")
    async def create(self, interaction: discord.Interaction, card: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("À utiliser dans un serveur.", ephemeral=True)
            return
        # Résout l'URL produit si on a reçu un nom
        url = card if card.startswith("http") else None
        if url is None:
            results = await self.bot.cardmarket.search(card, limit=1)
            if not results:
                await interaction.followup.send("Carte introuvable sur Cardmarket.", ephemeral=True)
                return
            url = results[0].url

        chan_name = ("mon-" + card.lower())[:90].replace(" ", "-")
        channel = await guild.create_text_channel(name=chan_name)
        monitor_id = await self.bot.db.execute(
            "INSERT INTO monitors(card_name, url, channel_id) VALUES(?, ?, ?)",
            (card, url, channel.id),
        )
        await interaction.followup.send(
            f"📈 Monitor #{monitor_id} créé : {channel.mention}", ephemeral=True
        )
        await self._update_one(
            await self.bot.db.fetchone("SELECT * FROM monitors WHERE id = ?", (monitor_id,))
        )

    @group.command(name="list", description="Liste les monitors actifs")
    async def list_(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall("SELECT id, card_name, channel_id FROM monitors ORDER BY id")
        if not rows:
            await interaction.response.send_message("Aucun monitor.", ephemeral=True)
            return
        lines = [f"**#{r['id']}** {r['card_name']} → <#{r['channel_id']}>" for r in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Supprime un monitor (le salon reste)")
    async def remove(self, interaction: discord.Interaction, id: int):
        await self.bot.db.execute("DELETE FROM monitors WHERE id = ?", (id,))
        await interaction.response.send_message(f"🗑️ Monitor #{id} supprimé.", ephemeral=True)

    # --- polling -------------------------------------------------------------
    @tasks.loop(minutes=MONITOR_POLL_MINUTES)
    async def poll_loop(self):
        rows = await self.bot.db.fetchall("SELECT * FROM monitors")
        for r in rows:
            try:
                await self._update_one(r)
            except Exception:  # noqa: BLE001
                log.exception("Échec update monitor #%s", r["id"])

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _update_one(self, row) -> None:
        if row is None:
            return
        detail = await self.bot.cardmarket.product_detail(row["url"])
        if detail.lowest_price is not None:
            await self.bot.db.record_price(
                "monitor", row["id"], detail.lowest_price, offers_count=detail.offers_count
            )
            await self.bot.db.execute(
                "UPDATE monitors SET last_lowest = ? WHERE id = ?",
                (detail.lowest_price, row["id"]),
            )
        channel = self.bot.get_channel(int(row["channel_id"]))
        if channel is None:
            return

        series = await self.bot.db.price_series("monitor", row["id"])
        rows_dicts = [dict(s) for s in series]
        t7 = trend_pct(window_prices(rows_dicts, 7))
        t30 = trend_pct(window_prices(rows_dicts, 30))

        embed = discord.Embed(title=f"📈 {detail.name}", url=detail.url, color=0xFFC107)
        if detail.lowest_price is not None:
            embed.add_field(name="Prix mini", value=f"{detail.lowest_price:.2f} €", inline=True)
        embed.add_field(name="Offres", value=str(detail.offers_count), inline=True)
        embed.add_field(
            name="Gradées / Raw", value=f"{detail.graded_count} / {detail.raw_count}", inline=True
        )
        if detail.by_condition:
            embed.add_field(
                name="Par état",
                value=", ".join(f"{k}: {v}" for k, v in detail.by_condition.items())[:1024],
                inline=False,
            )
        if detail.by_language:
            embed.add_field(
                name="Par langue",
                value=", ".join(f"{k}: {v}" for k, v in detail.by_language.items())[:1024],
                inline=False,
            )
        trend_str = " · ".join(
            s for s in [
                f"7j {t7:+.1%}" if t7 is not None else "",
                f"30j {t30:+.1%}" if t30 is not None else "",
            ] if s
        )
        if trend_str:
            embed.add_field(name="Tendance", value=trend_str, inline=False)

        file = None
        if len(rows_dicts) >= 2:
            png = build_price_chart(rows_dicts, detail.name)
            file = discord.File(io.BytesIO(png), filename="price.png")
            embed.set_image(url="attachment://price.png")
        await channel.send(embed=embed, file=file)


async def setup(bot: commands.Bot):
    await bot.add_cog(MonitorCog(bot))
