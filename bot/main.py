"""Point d'entrée : bootstrap discord.py + DB + scrapers + services + scheduler + cogs.

Lancement : `python -m bot.main` (ou via Docker, voir docker-compose.yml).
"""
from __future__ import annotations

import asyncio
import logging
import zoneinfo

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands

from bot.config import PricingConfig, get_settings
from bot.db import Database
from bot.scrapers.base import ScrapeClient
from bot.scrapers.cardmarket import CardmarketScraper
from bot.scrapers.ebay import EbayScraper
from bot.scrapers.japan import JapanScraper
from bot.scrapers.riftcodex import RiftcodexScraper
from bot.scrapers.vinted import VintedScraper
from bot.services.fx_wise import WiseFx
from bot.services.knowledge import KnowledgeBase

COGS = [
    "bot.cogs.config",
    "bot.cogs.tracking",
    "bot.cogs.sold",
    "bot.cogs.monitor",
    "bot.cogs.calc",
    "bot.cogs.arbitrage",
    "bot.cogs.grading",
    "bot.cogs.sealed",
    "bot.cogs.knowledge",
    "bot.cogs.cards",
    "bot.cogs.signals",
    "bot.cogs.daily",
]

log = logging.getLogger(__name__)


class TrackingBot(commands.Bot):
    """Bot conteneur : porte la DB, les scrapers, les services et le scheduler."""

    def __init__(self) -> None:
        self.settings = get_settings()
        intents = discord.Intents.default()
        intents.message_content = True  # nécessaire pour le salon calculateur (§3.5)
        super().__init__(command_prefix="!", intents=intents, help_command=None)

        self.tz = zoneinfo.ZoneInfo(self.settings.timezone)
        self.db = Database(self.settings.db_path)
        self.client = ScrapeClient()
        self.pricing = PricingConfig.load(self.settings.pricing_config)
        self.knowledge = KnowledgeBase(self.settings.knowledge_dir)
        self.scheduler = AsyncIOScheduler(timezone=self.tz)

        # scrapers + services partagés
        self.ebay = EbayScraper(self.client)
        self.vinted = VintedScraper(self.client)
        self.cardmarket = CardmarketScraper(self.client)
        self.japan = JapanScraper(self.client)
        self.riftcodex = RiftcodexScraper(self.client)
        self.fx = WiseFx(self.client)

    async def setup_hook(self) -> None:
        await self.db.connect()
        # Surcharge des taux par les overrides stockés en table config
        overrides = await self.db.config_get("pricing_overrides", default={})
        if overrides:
            self.pricing.apply_overrides(overrides)
        self.knowledge.load()
        await self.client.start()

        # Boutons d'action persistants (§3.10) : survivent aux redémarrages
        from bot.ui.alerts import AlertActionButton

        self.add_dynamic_items(AlertActionButton)

        for ext in COGS:
            try:
                await self.load_extension(ext)
                log.info("Cog chargé : %s", ext)
            except Exception:  # noqa: BLE001
                log.exception("Échec chargement cog %s", ext)

        # Sync des slash commands (guild en dev = instantané, sinon global)
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synchronisées sur la guild %s", self.settings.discord_guild_id)
        else:
            await self.tree.sync()
            log.info("Slash commands synchronisées globalement (propagation ~1 h)")

        self.scheduler.start()

    async def on_ready(self) -> None:
        log.info("Connecté en tant que %s (id=%s)", self.user, self.user.id if self.user else "?")

    async def close(self) -> None:
        log.info("Arrêt du bot…")
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.client.close()
        await self.db.close()
        await super().close()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )


async def _amain() -> None:
    bot = TrackingBot()
    _setup_logging(bot.settings.log_level)
    if not bot.settings.discord_token:
        raise SystemExit(
            "DISCORD_TOKEN manquant dans .env (renseigne le BOT TOKEN, pas le client secret)."
        )
    async with bot:
        await bot.start(bot.settings.discord_token)


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
