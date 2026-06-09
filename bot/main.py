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
from bot.scrapers.japan import MercariScraper
from bot.scrapers.riftcodex import RiftcodexScraper
from bot.scrapers.vinted import VintedScraper
from bot.services.fx_wise import WiseFx
from bot.services.knowledge import KnowledgeBase

COGS = [
    "bot.cogs.config",
    "bot.cogs.info",
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

    def __init__(self, *, enable_message_content: bool = True) -> None:
        self.settings = get_settings()
        intents = discord.Intents.default()
        # message_content (privilégié) : nécessaire pour la réponse auto du salon calculateur
        # (§3.5). Si l'intent n'est pas activé sur le portail, on démarre sans (mode dégradé).
        intents.message_content = enable_message_content
        self.message_content_enabled = enable_message_content
        super().__init__(command_prefix="!", intents=intents, help_command=None)

        self._synced = False
        try:
            self.tz = zoneinfo.ZoneInfo(self.settings.timezone)
        except (zoneinfo.ZoneInfoNotFoundError, ModuleNotFoundError):
            from datetime import timezone

            log.warning(
                "Fuseau '%s' introuvable (paquet tzdata manquant ?) → repli sur UTC.",
                self.settings.timezone,
            )
            self.tz = timezone.utc
        self.db = Database(self.settings.db_path)
        self.client = ScrapeClient()
        self.pricing = PricingConfig.load(self.settings.pricing_config)
        self.knowledge = KnowledgeBase(self.settings.knowledge_dir)
        self.scheduler = AsyncIOScheduler(timezone=self.tz)

        # scrapers + services partagés
        self.ebay = EbayScraper(self.client)
        self.vinted = VintedScraper(self.client)
        self.cardmarket = CardmarketScraper(self.client)
        self.japan = MercariScraper(self.client)
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

        # Si une guild est fixée : sync instantané ici. Sinon, on synchronise sur
        # tou(te)s les serveur(s) détecté(s) dans on_ready (instantané aussi).
        if self.settings.discord_guild_id:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synchronisées sur la guild %s", self.settings.discord_guild_id)
            self._synced = True

        self.scheduler.start()

    async def on_ready(self) -> None:
        log.info("Connecté en tant que %s (id=%s)", self.user, self.user.id if self.user else "?")
        # Auto-sync sur les serveurs où le bot est présent (sync instantané sans config).
        if not self._synced and self.guilds:
            for g in self.guilds:
                try:
                    self.tree.copy_global_to(guild=g)
                    await self.tree.sync(guild=g)
                    log.info("Slash commands synchronisées sur %s (%s)", g.name, g.id)
                except Exception:  # noqa: BLE001
                    log.exception("Échec sync sur la guild %s", g.id)
            self._synced = True
        elif not self.guilds:
            log.warning("Le bot n'est dans aucun serveur — invite-le avec scope bot+applications.commands.")

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


async def _run(token: str, enable_message_content: bool) -> None:
    bot = TrackingBot(enable_message_content=enable_message_content)
    async with bot:
        await bot.start(token)


async def _amain() -> None:
    settings = get_settings()
    _setup_logging(settings.log_level)
    if not settings.discord_token:
        raise SystemExit(
            "DISCORD_TOKEN manquant dans .env (renseigne le BOT TOKEN, pas le client secret)."
        )
    try:
        await _run(settings.discord_token, enable_message_content=True)
    except discord.errors.PrivilegedIntentsRequired:
        log.warning(
            "⚠️ MESSAGE CONTENT INTENT non activé sur le portail Discord → démarrage en MODE "
            "DÉGRADÉ : tout fonctionne SAUF la réponse automatique dans les salons calculateur "
            "(/calc compute et les autres commandes marchent). Pour l'activer : portail dev → "
            "ton appli → onglet Bot → 'MESSAGE CONTENT INTENT', puis redémarre."
        )
        await _run(settings.discord_token, enable_message_content=False)


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
