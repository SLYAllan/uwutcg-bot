"""Salon quotidien automatique (§3.3) + digest hebdomadaire (§5).

Jobs APScheduler (timezone Europe/Paris par défaut) :
- quotidien 09:00 : taux JPY→EUR Wise (fallback étiqueté) + synthèse de monitoring
  (variations notables des cartes suivies depuis la veille).
- hebdomadaire lundi 09:00 : récap deals saisis/ignorés + évolution des cotes suivies.
"""
from __future__ import annotations

import logging

import discord
from apscheduler.triggers.cron import CronTrigger
from discord.ext import commands

from bot.services.price_monitor import trend_pct, window_prices

log = logging.getLogger(__name__)


class DailyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.scheduler.add_job(
            self.daily_digest, CronTrigger(hour=9, minute=0), id="daily_digest", replace_existing=True
        )
        bot.scheduler.add_job(
            self.weekly_digest,
            CronTrigger(day_of_week="mon", hour=9, minute=0),
            id="weekly_digest",
            replace_existing=True,
        )

    async def _digest_channel(self):
        cid = await self.bot.db.config_get("daily_digest_channel_id")
        if cid is None:
            cid = self.bot.settings.daily_digest_channel_id
        return self.bot.get_channel(int(cid)) if cid else None

    # --- quotidien -----------------------------------------------------------
    async def daily_digest(self):
        channel = await self._digest_channel()
        if channel is None:
            log.warning("Salon digest non configuré (/config set-digest-channel).")
            return
        # 1) Taux de change
        try:
            rate = await self.bot.fx.get_rate()
            tag = " (fallback)" if rate.is_fallback else ""
            fx_line = f"**1 JPY = {rate.rate:.5f} €** · 1000 JPY = {rate.jpy_to_eur(1000):.2f} € — {rate.source}{tag}"
        except Exception as exc:  # noqa: BLE001
            fx_line = f"Taux indisponible : {exc}"

        embed = discord.Embed(title="☀️ Digest quotidien — UwUTCG", color=0xF1C40F)
        embed.add_field(name="💱 JPY → EUR (Wise)", value=fx_line, inline=False)

        # 2) Synthèse monitoring : UNIQUEMENT les cartes dont le prix a changé depuis hier.
        monitors = await self.bot.db.fetchall("SELECT * FROM monitors")
        changed: list[tuple[float, str]] = []
        for m in monitors:
            prices = window_prices(
                [dict(s) for s in await self.bot.db.price_series("monitor", m["id"])], 1
            )
            if len(prices) < 2:
                continue
            old, new = prices[0], prices[-1]
            if round(old, 2) == round(new, 2):
                continue  # pas de changement → on n'affiche pas (anti-spam)
            delta = new - old
            pct = (delta / old) if old else 0.0
            arrow = "🔻" if delta < 0 else "🔺"
            changed.append(
                (abs(pct), f"{arrow} **{m['card_name']}** {new:.2f} € ({delta:+.2f} € / {pct:+.1%})")
            )
        changed.sort(key=lambda x: x[0], reverse=True)  # plus grosses variations d'abord
        embed.add_field(
            name="📊 Cartes suivies (variations depuis hier)",
            value="\n".join(line for _, line in changed) if changed
            else "Aucun changement de prix depuis hier.",
            inline=False,
        )
        await channel.send(embed=embed)

    # --- hebdomadaire --------------------------------------------------------
    async def weekly_digest(self):
        channel = await self._digest_channel()
        if channel is None:
            return
        bought = await self.bot.db.fetchone(
            "SELECT COUNT(*) c FROM seen_listings WHERE status = 'bought' "
            "AND seen_at >= datetime('now', '-7 days')"
        )
        ignored = await self.bot.db.fetchone(
            "SELECT COUNT(*) c FROM seen_listings WHERE status = 'ignored' "
            "AND seen_at >= datetime('now', '-7 days')"
        )
        saved = await self.bot.db.fetchone(
            "SELECT COUNT(*) c FROM seen_listings WHERE status = 'saved' "
            "AND seen_at >= datetime('now', '-7 days')"
        )
        embed = discord.Embed(title="🗓️ Digest hebdomadaire", color=0x9B59B6)
        embed.add_field(
            name="Deals (7 j)",
            value=f"✅ {bought['c']} achetés · 📌 {saved['c']} sauvegardés · 🚫 {ignored['c']} ignorés",
            inline=False,
        )
        monitors = await self.bot.db.fetchall("SELECT * FROM monitors")
        lines = []
        for m in monitors:
            series = [dict(s) for s in await self.bot.db.price_series("monitor", m["id"], days=7)]
            t = trend_pct(window_prices(series, 7))
            if t is not None:
                lines.append(f"**{m['card_name']}** {t:+.1%} (7 j)")
        embed.add_field(name="Cotes suivies", value="\n".join(lines) or "—", inline=False)
        await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyCog(bot))
