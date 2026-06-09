"""Monitoring de prix détaillé d'une carte Cardmarket (§3.4).

/monitor create → publie dans un salon existant (salon courant par défaut) un
suivi détaillé mis à jour périodiquement (prix mini, nb offres, répartition
état/langue, gradées vs raw, historique construit par le bot, tendances 7j/30j,
graphique).
"""
from __future__ import annotations

import asyncio
import io
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.notify import PING_ALLOWED, add_subscriber, mention_prefix
from bot.scrapers.base import DomainCooldownError
from bot.services.price_monitor import build_price_chart, trend_pct, window_prices

log = logging.getLogger(__name__)

MONITOR_POLL_MINUTES = 180  # 3 h : Cardmarket via Playwright, on espace les hits

GAME_CHOICES = [
    app_commands.Choice(name="Pokémon", value="pokemon"),
    app_commands.Choice(name="Riftbound", value="riftbound"),
]


class MonitorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="monitor", description="Suivi détaillé d'une carte Cardmarket")

    @group.command(name="create", description="Suit une carte dans un salon existant")
    @app_commands.choices(game=GAME_CHOICES)
    @app_commands.describe(
        card="Nom de la carte ou URL Cardmarket",
        salon="Salon où publier le suivi (défaut : salon courant)",
        game="Jeu Cardmarket pour la recherche par nom (défaut : Pokémon)",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        card: str,
        salon: discord.TextChannel | None = None,
        game: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("À utiliser dans un serveur.", ephemeral=True)
            return
        channel = salon or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Salon invalide : utilise un salon textuel.", ephemeral=True)
            return
        # Résout l'URL produit si on a reçu un nom
        url = card if card.startswith("http") else None
        if url is None:
            results = await self.bot.cardmarket.search(
                card, limit=1, game=game.value if game else "pokemon"
            )
            if not results:
                await interaction.followup.send("Carte introuvable sur Cardmarket.", ephemeral=True)
                return
            url = results[0].url

        monitor_id = await self.bot.db.execute(
            "INSERT INTO monitors(card_name, url, channel_id) VALUES(?, ?, ?)",
            (card, url, channel.id),
        )
        await add_subscriber(self.bot.db, interaction.user.id)  # le créateur est pingué
        await interaction.followup.send(
            f"📈 Monitor #{monitor_id} créé dans {channel.mention}", ephemeral=True
        )
        await self._update_one(
            await self.bot.db.fetchone("SELECT * FROM monitors WHERE id = ?", (monitor_id,)),
            force=True,  # 1re fiche publiée à la création même si pas de variation
        )

    @group.command(name="bulk", description="Crée plusieurs monitors d'un coup (cartes séparées par ;)")
    @app_commands.choices(game=GAME_CHOICES)
    @app_commands.describe(
        cards="Noms ou URLs Cardmarket séparés par ; (URLs recommandées : pas de recherche)",
        salon="Salon où publier les suivis (défaut : salon courant)",
        game="Jeu Cardmarket pour la recherche par nom (défaut : Pokémon)",
    )
    async def bulk(
        self,
        interaction: discord.Interaction,
        cards: str,
        salon: discord.TextChannel | None = None,
        game: app_commands.Choice[str] | None = None,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)
        if interaction.guild is None:
            await interaction.followup.send("À utiliser dans un serveur.", ephemeral=True)
            return
        channel = salon or interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Salon invalide : utilise un salon textuel.", ephemeral=True)
            return
        items = [s.strip() for s in cards.split(";") if s.strip()]
        if not items:
            await interaction.followup.send("Aucune carte — sépare-les par `;`.", ephemeral=True)
            return
        created: list[int] = []
        skipped: list[str] = []
        for item in items:
            if item.startswith("http"):
                url = item
                name = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            else:
                results = await self.bot.cardmarket.search(
                    item, limit=1, game=game.value if game else "pokemon"
                )
                if not results:
                    skipped.append(item)
                    continue
                url, name = results[0].url, item
            monitor_id = await self.bot.db.execute(
                "INSERT INTO monitors(card_name, url, channel_id) VALUES(?, ?, ?)",
                (name, url, channel.id),
            )
            created.append(monitor_id)
        await add_subscriber(self.bot.db, interaction.user.id)
        msg = (
            f"📈 {len(created)}/{len(items)} monitors créés dans {channel.mention} — "
            "les premières fiches arrivent au fil de l'eau."
        )
        if skipped:
            msg += "\n⚠️ Introuvables : " + ", ".join(f"`{s}`" for s in skipped)
        await interaction.followup.send(msg[:1990], ephemeral=True)
        # Publication initiale en arrière-plan : 1 fetch Cardmarket par carte (rate-limité).
        asyncio.create_task(self._seed_new(created))

    async def _seed_new(self, ids: list[int]) -> None:
        for mid in ids:
            row = await self.bot.db.fetchone("SELECT * FROM monitors WHERE id = ?", (mid,))
            try:
                await self._update_one(row, force=True)
            except DomainCooldownError as e:
                # Les fiches restantes seront publiées au prochain cycle de poll.
                log.warning("Publication initiale interrompue (anti-ban) : %s", e)
                break
            except Exception:  # noqa: BLE001
                log.exception("Échec publication initiale monitor #%s", mid)

    @group.command(name="list", description="Liste les monitors actifs")
    async def list_(self, interaction: discord.Interaction):
        rows = await self.bot.db.fetchall("SELECT id, card_name, channel_id FROM monitors ORDER BY id")
        if not rows:
            await interaction.response.send_message("Aucun monitor.", ephemeral=True)
            return
        lines = [f"**#{r['id']}** {r['card_name']} → <#{r['channel_id']}>" for r in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @group.command(name="remove", description="Supprime un monitor")
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
            except DomainCooldownError as e:
                # Ban détecté : inutile d'enchaîner les autres monitors du même domaine.
                log.warning("Monitors suspendus (anti-ban) : %s", e)
                break
            except Exception:  # noqa: BLE001
                log.exception("Échec update monitor #%s", r["id"])

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _update_one(self, row, force: bool = False) -> None:
        if row is None:
            return
        detail = await self.bot.cardmarket.product_detail(row["url"])
        # Page sans la moindre donnée produit (challenge Cloudflare, HTML inattendu…) :
        # on ne publie PAS de fiche vide, le prochain cycle réessaiera.
        if detail.lowest_price is None and not (detail.total_available or detail.offers_count):
            log.warning("Monitor #%s : page produit sans données, fiche non publiée (%s)",
                        row["id"], row["url"])
            return
        prev = row["last_lowest"]
        # On enregistre toujours l'historique (pour le graphique/tendance)…
        if detail.lowest_price is not None:
            await self.bot.db.record_price(
                "monitor", row["id"], detail.lowest_price,
                offers_count=detail.total_available or detail.offers_count,
            )
            await self.bot.db.execute(
                "UPDATE monitors SET last_lowest = ? WHERE id = ?",
                (detail.lowest_price, row["id"]),
            )
        # …mais on ne NOTIFIE que si le prix mini a CHANGÉ (ou 1er passage) → anti-spam.
        has_price = detail.lowest_price is not None
        changed = force or (
            has_price and (prev is None or round(float(prev), 2) != round(detail.lowest_price, 2))
        )
        if not changed:
            return
        channel = self.bot.get_channel(int(row["channel_id"]))
        if channel is None:
            return

        series = await self.bot.db.price_series("monitor", row["id"])
        rows_dicts = [dict(s) for s in series]
        t7 = trend_pct(window_prices(rows_dicts, 7))
        t30 = trend_pct(window_prices(rows_dicts, 30))

        # Couleur selon le sens de variation (vert = baisse = bonne affaire).
        color = 0xFFC107
        if has_price and prev is not None:
            color = 0x2ECC71 if detail.lowest_price < float(prev) else 0xE74C3C
        embed = discord.Embed(title=f"📈 {detail.name}", url=detail.url, color=color)
        if detail.lowest_price is not None:
            val = f"{detail.lowest_price:.2f} €"
            if prev is not None and round(float(prev), 2) != round(detail.lowest_price, 2):
                arrow = "🔻" if detail.lowest_price < float(prev) else "🔺"
                val += f"  {arrow} (avant {float(prev):.2f} €)"
            embed.add_field(name="Prix mini", value=val, inline=True)
        # Vrai total dispo (en-tête Cardmarket), pas seulement les offres affichées.
        offres = str(detail.total_available) if detail.total_available is not None else str(detail.offers_count)
        embed.add_field(name="Offres dispo", value=offres, inline=True)
        # Tendance & moyennes officielles Cardmarket (fiables, immédiates).
        cm_trend = " · ".join(
            s for s in [
                f"tendance {detail.trend_price:.2f} €" if detail.trend_price else "",
                f"7j {detail.avg_7d:.2f} €" if detail.avg_7d else "",
                f"30j {detail.avg_30d:.2f} €" if detail.avg_30d else "",
            ] if s
        )
        if cm_trend:
            embed.add_field(name="Prix moyens (CM)", value=cm_trend, inline=False)
        # Répartition sur les offres AFFICHÉES (page 1) — étiquetée comme telle.
        shown = detail.offers_count
        if detail.by_condition:
            embed.add_field(
                name=f"Par état (sur {shown} affichées)",
                value=", ".join(f"{k}: {v}" for k, v in detail.by_condition.items())[:1024],
                inline=False,
            )
        embed.add_field(
            name="Gradées / Raw (affichées)",
            value=f"{detail.graded_count} / {detail.raw_count}",
            inline=True,
        )
        # Tendance construite par le bot sur son propre historique (complément).
        bot_trend = " · ".join(
            s for s in [
                f"7j {t7:+.1%}" if t7 is not None else "",
                f"30j {t30:+.1%}" if t30 is not None else "",
            ] if s
        )
        if bot_trend:
            embed.add_field(name="Évolution suivie (bot)", value=bot_trend, inline=True)

        file = None
        if len(rows_dicts) >= 2:
            png = build_price_chart(rows_dicts, detail.name)
            file = discord.File(io.BytesIO(png), filename="price.png")
            embed.set_image(url="attachment://price.png")
        mentions = await mention_prefix(self.bot.db)
        await channel.send(content=mentions, embed=embed, file=file, allowed_mentions=PING_ALLOWED)


async def setup(bot: commands.Bot):
    await bot.add_cog(MonitorCog(bot))
