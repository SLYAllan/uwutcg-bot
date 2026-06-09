"""Suivi de produits scellés Riftbound & Pokémon (§3.8).

/sealed watch | list | remove. Suit le prix dans le temps (price_history), alerte sous
un seuil d'achat. Croise avec la knowledge base pour reconnaître les noms de sets.
"""
from __future__ import annotations

import logging
from statistics import median

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger(__name__)

SEALED_POLL_MINUTES = 120


class SealedCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="sealed", description="Suivi de produits scellés")

    @group.command(name="watch", description="Surveille un produit scellé")
    @app_commands.describe(product="Nom du produit (display, ETB, coffret…)", buy_below="Alerte si prix ≤ (€)")
    async def watch(
        self, interaction: discord.Interaction, product: str, buy_below: float | None = None
    ):
        wid = await self.bot.db.execute(
            "INSERT INTO sealed_watches(product, buy_below, channel_id) VALUES(?, ?, ?)",
            (product, buy_below, interaction.channel.id),
        )
        # Reconnaissance du set via knowledge (best effort, juste informatif)
        hint = ""
        for doc in ("riftbound", "pokemon"):
            sec = self.bot.knowledge.best_section(doc, product)
            if sec:
                hint = f" · reconnu dans `{doc}` → *{sec.title}*"
                break
        await interaction.response.send_message(
            f"📦 Scellé #{wid} : `{product}`"
            + (f" (alerte ≤ {buy_below:.2f} €)" if buy_below else "")
            + hint,
            ephemeral=True,
        )

    @group.command(name="list", description="Liste les produits scellés suivis")
    async def list_(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall("SELECT id, product, buy_below FROM sealed_watches ORDER BY id")
        if not rows:
            await interaction.response.send_message("Aucun scellé suivi.", ephemeral=True)
            return
        lines = [
            f"**#{r['id']}** `{r['product']}`" + (f" ≤{r['buy_below']:.0f}€" if r["buy_below"] else "")
            for r in rows
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Supprime un suivi de scellé")
    async def remove(self, interaction: discord.Interaction, id: int):
        await self.bot.db.execute("DELETE FROM sealed_watches WHERE id = ?", (id,))
        await interaction.response.send_message(f"🗑️ Scellé #{id} supprimé.", ephemeral=True)

    # --- polling -------------------------------------------------------------
    @tasks.loop(minutes=SEALED_POLL_MINUTES)
    async def poll_loop(self):
        rows = await self.bot.db.fetchall("SELECT * FROM sealed_watches")
        for r in rows:
            try:
                await self._check(r)
            except Exception:  # noqa: BLE001
                log.exception("Échec scellé #%s", r["id"])

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _check(self, r) -> None:
        items = await self.bot.ebay.search_active(r["product"])
        prices = sorted(i.price for i in items if i.price is not None)
        if not prices:
            return
        lowest = prices[0]
        await self.bot.db.record_price("sealed", r["id"], lowest, offers_count=len(prices))
        if r["buy_below"] and lowest <= r["buy_below"]:
            channel = self.bot.get_channel(int(r["channel_id"]))
            if channel:
                embed = discord.Embed(
                    title=f"📦 Scellé sous seuil — {r['product']}",
                    description=(
                        f"Prix mini **{lowest:.2f} €** ≤ seuil {r['buy_below']:.2f} € · "
                        f"médiane {median(prices):.2f} € ({len(prices)} offres)"
                    ),
                    color=0x2ECC71,
                )
                await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SealedCog(bot))
