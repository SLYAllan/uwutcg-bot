"""Vinted : la session doit échouer FORT si le cookie d'accès manque.

Sans le cookie access_token_web, l'API répond 401 sur chaque appel. Le scraper doit
le dire clairement au lieu de laisser passer et boucler sur des 401.
"""
import httpx
import pytest

from bot.scrapers.vinted import VintedScraper, VintedSessionError


class _FakeClient:
    """ScrapeClient minimal : on choisit les cookies que la « home » pose."""

    def __init__(self, cookies: dict, pose: dict | None = None):
        self.cookies = httpx.Cookies()
        for k, v in cookies.items():
            self.cookies.set(k, v, domain=".vinted.fr")
        self.pose = pose or {}   # cookies posés par la « home » à chaque visite
        self.visits = 0

    async def start(self):
        pass

    async def get(self, url, **kwargs):
        self.visits += 1
        for k, v in self.pose.items():
            # Comme le vrai Vinted : la home ne réémet RIEN si le cookie est déjà là.
            if k not in self.cookies:
                self.cookies.set(k, v, domain=".vinted.fr")
        return None


@pytest.mark.asyncio
async def test_session_ko_sans_cookie_acces():
    s = VintedScraper(_FakeClient({"__cf_bm": "x", "anon_id": "y"}))
    with pytest.raises(VintedSessionError) as e:
        await s._ensure_session()
    assert "access_token_web" in str(e.value)
    assert "anon_id" in str(e.value)  # dit ce qui a VRAIMENT été posé
    assert s._session_ready is False


@pytest.mark.asyncio
async def test_session_ok_avec_cookie_acces():
    client = _FakeClient({"access_token_web": "jeton"})
    s = VintedScraper(client)
    await s._ensure_session()
    assert s._session_ready is True
    await s._ensure_session()  # 2e appel : pas de nouvelle visite
    assert client.visits == 1


@pytest.mark.asyncio
async def test_force_jette_la_session_perimee():
    """Le cas qui coupait le bot : session pourrie, réparée seulement par un redéploiement.

    Sans purge, le vieux jeton reste dans le jar et l'API répond 401 sans fin.
    """
    client = _FakeClient({"access_token_web": "perime"}, pose={"access_token_web": "neuf"})
    client.cookies.set("autre", "garde", domain="example.com")  # autre scraper : intact
    s = VintedScraper(client)
    await s._ensure_session(force=True)
    assert client.cookies.get("access_token_web") == "neuf"
    assert client.cookies.get("autre", domain="example.com") == "garde"
