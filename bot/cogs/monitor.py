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
from urllib.parse import urlsplit

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.notify import PING_ALLOWED, add_subscriber, mention_prefix
from bot.scrapers.base import DomainCooldownError
from bot.scrapers.cardmarket import CM_LANGUAGES, apply_language
from bot.services.price_monitor import build_price_chart, trend_pct, window_prices

log = logging.getLogger(__name__)

MONITOR_POLL_MINUTES = 180  # 3 h : Cardmarket via Playwright, on espace les hits

GAME_CHOICES = [
    app_commands.Choice(name="Pokémon", value="pokemon"),
    app_commands.Choice(name="Riftbound", value="riftbound"),
]

# Choix de langue Cardmarket. value "0" = toutes langues (aucun filtre).
LANG_CHOICES = [
    app_commands.Choice(name="Toutes langues", value="0"),
    app_commands.Choice(name="Français", value="2"),
    app_commands.Choice(name="Anglais", value="1"),
    app_commands.Choice(name="Japonais", value="7"),
    app_commands.Choice(name="Allemand", value="3"),
    app_commands.Choice(name="Italien", value="5"),
    app_commands.Choice(name="Espagnol", value="4"),
]


def _lang_value(choice: app_commands.Choice[str] | None) -> str | None:
    """Choice langue → id stocké en base (None = toutes langues)."""
    if choice is None or choice.value == "0":
        return None
    return choice.value


def _tags(lang: str | None, threshold: float | None) -> str:
    """Suffixe d'affichage « (Français · ≤ 50 €) » pour confirmations et listes."""
    parts = []
    if lang and lang in CM_LANGUAGES:
        parts.append(CM_LANGUAGES[lang])
    if threshold is not None:
        parts.append(f"≤ {threshold:.2f} €")
    return f" ({' · '.join(parts)})" if parts else ""


class MonitorCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Décalage de départ du balayage : avance après chaque cooldown anti-ban pour
        # que les derniers monitors ne soient pas systématiquement affamés (voir poll_loop).
        self._poll_offset = 0
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    group = app_commands.Group(name="monitor", description="Suivi détaillé d'une carte Cardmarket")

    @group.command(name="create", description="Suit une carte dans un salon existant")
    @app_commands.choices(game=GAME_CHOICES, langue=LANG_CHOICES)
    @app_commands.describe(
        card="Nom de la carte ou URL Cardmarket",
        salon="Salon où publier le suivi (défaut : salon courant)",
        game="Jeu Cardmarket pour la recherche par nom (défaut : Pokémon)",
        langue="Langue des cartes à suivre (défaut : toutes)",
        seuil="Alerte seuil (€) : ne ping que si le prix mini passe sous ce montant",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        card: str,
        salon: discord.TextChannel | None = None,
        game: app_commands.Choice[str] | None = None,
        langue: app_commands.Choice[str] | None = None,
        seuil: app_commands.Range[float, 0.0] | None = None,
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

        lang = _lang_value(langue)
        monitor_id = await self.bot.db.execute(
            "INSERT INTO monitors(card_name, url, channel_id, language, threshold) "
            "VALUES(?, ?, ?, ?, ?)",
            (card, url, channel.id, lang, seuil),
        )
        await add_subscriber(self.bot.db, interaction.user.id)  # le créateur est pingué
        await interaction.followup.send(
            f"📈 Monitor #{monitor_id}{_tags(lang, seuil)} créé dans {channel.mention}",
            ephemeral=True,
        )
        await self._update_one(
            await self.bot.db.fetchone("SELECT * FROM monitors WHERE id = ?", (monitor_id,)),
            force=True,  # 1re fiche publiée à la création même si pas de variation
        )

    @group.command(name="bulk", description="Crée plusieurs monitors d'un coup (cartes séparées par ;)")
    @app_commands.choices(game=GAME_CHOICES, langue=LANG_CHOICES)
    @app_commands.describe(
        cards="Noms ou URLs Cardmarket séparés par ; (URLs recommandées : pas de recherche)",
        salon="Salon où publier les suivis (défaut : salon courant)",
        game="Jeu Cardmarket pour la recherche par nom (défaut : Pokémon)",
        langue="Langue des cartes à suivre (défaut : toutes)",
        seuil="Alerte seuil (€) appliquée à tous : ne ping que sous ce montant",
    )
    async def bulk(
        self,
        interaction: discord.Interaction,
        cards: str,
        salon: discord.TextChannel | None = None,
        game: app_commands.Choice[str] | None = None,
        langue: app_commands.Choice[str] | None = None,
        seuil: app_commands.Range[float, 0.0] | None = None,
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
        lang = _lang_value(langue)
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
                "INSERT INTO monitors(card_name, url, channel_id, language, threshold) "
                "VALUES(?, ?, ?, ?, ?)",
                (name, url, channel.id, lang, seuil),
            )
            created.append(monitor_id)
        await add_subscriber(self.bot.db, interaction.user.id)
        msg = (
            f"📈 {len(created)}/{len(items)} monitors{_tags(lang, seuil)} créés dans "
            f"{channel.mention} — les premières fiches arrivent au fil de l'eau."
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
        rows = await self.bot.db.fetchall(
            "SELECT id, card_name, channel_id, language, threshold, paused "
            "FROM monitors ORDER BY id"
        )
        if not rows:
            await interaction.response.send_message("Aucun monitor.", ephemeral=True)
            return
        lines = []
        for r in rows:
            pause = "⏸️ " if r["paused"] else ""
            lines.append(
                f"{pause}**#{r['id']}** {r['card_name']}{_tags(r['language'], r['threshold'])}"
                f" → <#{r['channel_id']}>"
            )
        # Découpe en messages ≤ 2000 car. (la limite Discord) : sinon /monitor list
        # plante dès qu'il y a beaucoup de monitors (créés via /monitor bulk).
        chunks: list[str] = []
        buf = ""
        for line in lines:
            if len(buf) + len(line) + 1 > 1900:
                chunks.append(buf)
                buf = ""
            buf += line + "\n"
        if buf:
            chunks.append(buf)
        await interaction.response.send_message(chunks[0], ephemeral=True)
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk, ephemeral=True)

    @group.command(name="remove", description="Supprime un monitor")
    async def remove(self, interaction: discord.Interaction, id: int):
        await self.bot.db.execute("DELETE FROM monitors WHERE id = ?", (id,))
        await interaction.response.send_message(f"🗑️ Monitor #{id} supprimé.", ephemeral=True)

    @group.command(name="pause", description="Met un monitor en pause (plus de poll ni de ping)")
    async def pause(self, interaction: discord.Interaction, id: int):
        await self._set_paused(interaction, id, True)

    @group.command(name="resume", description="Relance un monitor en pause")
    async def resume(self, interaction: discord.Interaction, id: int):
        await self._set_paused(interaction, id, False)

    async def _set_paused(self, interaction: discord.Interaction, id: int, paused: bool) -> None:
        row = await self.bot.db.fetchone("SELECT id FROM monitors WHERE id = ?", (id,))
        if row is None:
            await interaction.response.send_message(f"Monitor #{id} introuvable.", ephemeral=True)
            return
        await self.bot.db.execute(
            "UPDATE monitors SET paused = ? WHERE id = ?", (1 if paused else 0, id)
        )
        verb = "⏸️ en pause" if paused else "▶️ relancé"
        await interaction.response.send_message(f"Monitor #{id} {verb}.", ephemeral=True)

    @group.command(name="edit", description="Modifie langue / salon / seuil d'un monitor")
    @app_commands.choices(langue=LANG_CHOICES)
    @app_commands.describe(
        id="ID du monitor (voir /monitor list)",
        langue="Nouvelle langue Cardmarket",
        salon="Nouveau salon de publication",
        seuil="Nouveau seuil d'alerte (€). Mets 0 pour le retirer.",
    )
    async def edit(
        self,
        interaction: discord.Interaction,
        id: int,
        langue: app_commands.Choice[str] | None = None,
        salon: discord.TextChannel | None = None,
        seuil: app_commands.Range[float, 0.0] | None = None,
    ):
        row = await self.bot.db.fetchone("SELECT id FROM monitors WHERE id = ?", (id,))
        if row is None:
            await interaction.response.send_message(f"Monitor #{id} introuvable.", ephemeral=True)
            return
        sets: list[str] = []
        params: list = []
        if langue is not None:
            sets.append("language = ?")
            params.append(_lang_value(langue))
        if salon is not None:
            sets.append("channel_id = ?")
            params.append(salon.id)
        if seuil is not None:
            # 0 = on retire le seuil (NULL) → repasse en notif à chaque variation.
            sets.append("threshold = ?")
            params.append(None if seuil == 0 else seuil)
        if not sets:
            await interaction.response.send_message(
                "Rien à modifier : précise langue, salon ou seuil.", ephemeral=True
            )
            return
        params.append(id)
        await self.bot.db.execute(
            f"UPDATE monitors SET {', '.join(sets)} WHERE id = ?", params
        )
        await interaction.response.send_message(f"✏️ Monitor #{id} mis à jour.", ephemeral=True)

    # --- polling -------------------------------------------------------------
    @tasks.loop(minutes=MONITOR_POLL_MINUTES)
    async def poll_loop(self):
        rows = await self.bot.db.fetchall(
            "SELECT * FROM monitors WHERE paused = 0 ORDER BY id"
        )
        if not rows:
            return
        # Rotation anti-famine : on démarre là où le cycle précédent a calé sur un
        # cooldown anti-ban. Sinon, avec beaucoup de monitors, le même cooldown coupe
        # toujours au même endroit et les DERNIERS monitors ne sont jamais pollés.
        n = len(rows)
        start = self._poll_offset % n
        ordered = rows[start:] + rows[:start]
        cooled: set[str] = set()
        resume_at: int | None = None
        for i, r in enumerate(ordered):
            domain = urlsplit(r["url"]).netloc or "?"
            if domain in cooled:
                # Domaine déjà en cooldown ce cycle-ci : on saute sans toucher le réseau
                # et on note le 1er non-traité pour reprendre ici au prochain cycle.
                if resume_at is None:
                    resume_at = (start + i) % n
                continue
            try:
                await self._update_one(r)
            except DomainCooldownError as e:
                # Ban détecté : on reporte ce domaine (et ses monitors suivants) au
                # prochain cycle, mais on N'ABORTE PAS tout — d'autres domaines passent.
                log.warning("Domaine %s en cooldown (anti-ban) : %s", domain, e)
                cooled.add(domain)
                if resume_at is None:
                    resume_at = (start + i) % n
            except Exception:  # noqa: BLE001
                log.exception("Échec update monitor #%s", r["id"])
        # Cycle complet sans cooldown → on repart du début ; sinon reprise au point calé.
        self._poll_offset = resume_at if resume_at is not None else 0

    @poll_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _resolve_channel(self, channel_id):
        """Salon de publication, avec fallback API si le cache n'est pas peuplé.

        get_channel ne lit que le cache (vide juste après un redémarrage) → sans
        fallback fetch_channel, _update_one abandonnait SILENCIEUSEMENT et aucune
        fiche n'était publiée. On log explicitement si le salon est inaccessible.
        """
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except discord.HTTPException as exc:
                log.error(
                    "Monitor : salon %s inaccessible (supprimé ? bot absent du salon ?) : %s",
                    channel_id, exc,
                )
                return None
        return channel

    async def _update_one(self, row, force: bool = False) -> None:
        if row is None:
            return
        lang = row["language"]
        detail = await self.bot.cardmarket.product_detail(apply_language(row["url"], lang))
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
        # Alerte seuil : si un seuil est défini, on ne ping que quand le prix est SOUS
        # le seuil. La 1re fiche (force, à la création) passe toujours, à titre informatif.
        threshold = row["threshold"]
        if not force and threshold is not None and (not has_price or detail.lowest_price > threshold):
            return
        channel = await self._resolve_channel(row["channel_id"])
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
        lang_label = CM_LANGUAGES.get(lang) if lang else None
        title = f"📈 {detail.name}" + (f" · {lang_label}" if lang_label else "")
        embed = discord.Embed(title=title, url=detail.url, color=color)
        if threshold is not None:
            embed.set_footer(text=f"🔔 Alerte seuil ≤ {threshold:.2f} €")
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
        try:
            await channel.send(
                content=mentions, embed=embed, file=file, allowed_mentions=PING_ALLOWED
            )
        except discord.Forbidden:
            # Cause n°1 du « monitor créé mais aucune fiche reçue » : le bot n'a pas le
            # droit d'écrire dans ce salon. On le dit clairement dans les logs.
            log.error(
                "Monitor #%s : envoi REFUSÉ dans #%s — le bot n'a pas la permission "
                "« Envoyer des messages » dans ce salon.",
                row["id"], getattr(channel, "name", row["channel_id"]),
            )
        except discord.HTTPException as exc:
            log.error(
                "Monitor #%s : échec d'envoi dans #%s : %s",
                row["id"], getattr(channel, "name", row["channel_id"]), exc,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(MonitorCog(bot))
