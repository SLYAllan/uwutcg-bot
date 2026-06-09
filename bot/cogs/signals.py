"""Détecteur de pic / vélocité en arrière-plan (§3.9).

Scanne l'historique (price_history) des monitors et des scellés ; alerte sur pic de prix
(+X % sur la médiane) ou pic de volume (xN). Seuils dans pricing.yaml (thresholds).
"""
from __future__ import annotations

import logging

import discord
from discord.ext import commands, tasks

from bot.services.signals import detect_price_spike, detect_volume_spike

log = logging.getLogger(__name__)

SIGNALS_POLL_MINUTES = 240


class SignalsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scan_loop.start()

    def cog_unload(self):
        self.scan_loop.cancel()

    @tasks.loop(minutes=SIGNALS_POLL_MINUTES)
    async def scan_loop(self):
        th = self.bot.pricing.thresholds
        price_th = float(th.get("spike_price_pct_7d", 0.15))
        vol_factor = float(th.get("spike_volume_factor", 2.0))
        for subject_type, table in (("monitor", "monitors"), ("sealed", "sealed_watches")):
            rows = await self.bot.db.fetchall(f"SELECT * FROM {table}")
            for r in rows:
                try:
                    await self._scan_subject(subject_type, r, price_th, vol_factor)
                except Exception:  # noqa: BLE001
                    log.exception("Échec scan signal %s #%s", subject_type, r["id"])

    @scan_loop.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    async def _scan_subject(self, subject_type, r, price_th, vol_factor) -> None:
        series = await self.bot.db.price_series(subject_type, r["id"], days=7)
        if len(series) < 3:
            return
        prices = [float(s["price"]) for s in series]
        volumes = [int(s["offers_count"]) for s in series if s["offers_count"] is not None]
        current_price = prices[-1]
        price_spike = detect_price_spike(current_price, prices[:-1], price_th)

        vol_spike = None
        if len(volumes) >= 3:
            vol_spike = detect_volume_spike(volumes[-1], volumes[:-1], vol_factor)

        triggered = [s for s in (price_spike, vol_spike) if s and s.triggered]
        if not triggered:
            return
        channel = self.bot.get_channel(int(r["channel_id"])) if r["channel_id"] else None
        if channel is None:
            return
        name = r["card_name"] if "card_name" in r.keys() else r["product"]
        e = discord.Embed(title=f"⚡ Pic détecté — {name}", color=0xE74C3C)
        for s in triggered:
            e.add_field(name=f"Pic {s.kind}", value=s.detail, inline=False)
        await channel.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(SignalsCog(bot))
