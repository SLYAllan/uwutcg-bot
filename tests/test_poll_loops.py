"""Les boucles de fond ne doivent JAMAIS laisser sortir une exception.

discord.py n'en réessaye qu'une poignée (réseau) ; tout le reste arrête la boucle
définitivement et le bot cesse d'alerter en silence. On appelle donc la coroutine
des deux boucles avec une DB qui casse, et on vérifie que rien ne remonte.
"""
import pytest

from bot.cogs.monitor import MonitorCog
from bot.cogs.tracking import TrackingCog


class _BrokenDB:
    async def fetchall(self, *a, **k):
        raise RuntimeError("base indisponible")

    async def config_get(self, *a, **k):
        raise RuntimeError("base indisponible")


class _Bot:
    db = _BrokenDB()


class _Self:
    """Faux `self` : on appelle la coroutine brute, sans instancier le cog."""

    bot = _Bot()
    _last: dict = {}
    _inflight: set = set()
    _poll_offset = 0

    _intervals = TrackingCog._intervals
    _tick = TrackingCog._tick
    _sweep = MonitorCog._sweep


@pytest.mark.parametrize("cog", [TrackingCog, MonitorCog])
@pytest.mark.asyncio
async def test_poll_loop_survives_db_failure(cog):
    await cog.poll_loop.coro(_Self())  # ne doit rien lever
