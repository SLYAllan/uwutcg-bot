"""Le monitor ne doit plus partir en rafale : c'est ce qui a fait bannir l'IP.

Avant, un cycle balayait TOUS les monitors d'affilee (200 pages en ~25 min, 8x/jour).
On verifie ici qu'un tour ne prend qu'une carte, et que sur une journee simulee le
volume tient la fraicheur visee sans depasser une page par carte.
"""
import pytest

from bot.cogs.monitor import MONITOR_REFRESH_HOURS, MONITOR_TICK_SECONDS, MonitorCog


class _DB:
    def __init__(self, n):
        self.rows = [{"id": i, "url": f"https://www.cardmarket.com/c{i}", "paused": 0}
                     for i in range(n)]

    async def fetchall(self, *a, **k):
        return self.rows


class _Self:
    """Faux `self` : on appelle la coroutine brute, sans instancier le cog."""

    def __init__(self, n):
        self.bot = type("B", (), {"db": _DB(n)})()
        self._last = {}
        self.vus = []

    _sweep = MonitorCog._sweep

    async def _update_one(self, row, force=False):
        self.vus.append(row["id"])


@pytest.mark.asyncio
async def test_un_seul_monitor_par_tour():
    s = _Self(200)
    await s._sweep()
    assert len(s.vus) <= 1, "un tour doit prendre une carte au plus, jamais une rafale"


@pytest.mark.asyncio
async def test_volume_d_une_journee(monkeypatch):
    """200 cartes sur 24 h : chacune revue une fois, pas plus."""
    n = 200
    s = _Self(n)
    horloge = {"t": 0.0}
    monkeypatch.setattr("bot.cogs.monitor.time.monotonic", lambda: horloge["t"])

    tours = int(MONITOR_REFRESH_HOURS * 3600 / MONITOR_TICK_SECONDS)
    for _ in range(tours):
        await s._sweep()
        horloge["t"] += MONITOR_TICK_SECONDS

    assert len(s.vus) <= n, f"{len(s.vus)} pages pour {n} cartes : le volume derape"
    # Chaque carte au plus une fois : pas de carte pollee en boucle pendant que
    # d'autres sont affamees (le defaut que corrigeait l'ancien decalage anti-famine).
    assert max(s.vus.count(i) for i in range(n)) <= 1
    # Et la couverture reste utile : la grande majorite des cartes est bien passee.
    assert len(set(s.vus)) >= n * 0.9
