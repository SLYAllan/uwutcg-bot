"""Repli Firecrawl : il ne doit servir QUE si le navigateur est bloqué.

Chaque appel coûte un crédit. Un repli qui se déclencherait en temps normal, ou qui
masquerait une vraie panne, coûterait de l'argent pour rien.
"""
import pathlib

import pytest

from bot.scrapers.base import DomainCooldownError, ScrapeClient, is_blocked

BLOCAGE_REEL = pathlib.Path(__file__).parent / "fixtures" / "cloudflare_block.html"


def _client(monkeypatch, *, cle: str, firecrawl_html: str | None):
    c = ScrapeClient()
    monkeypatch.setattr("bot.scrapers.base.get_settings",
                        lambda: type("S", (), {"firecrawl_api_key": cle})())
    appels = {"navigateur": 0, "firecrawl": 0}

    async def _firecrawl(url):
        appels["firecrawl"] += 1
        return firecrawl_html

    monkeypatch.setattr(c, "_render_firecrawl", _firecrawl)
    return c, appels


@pytest.mark.asyncio
async def test_pas_de_repli_quand_le_navigateur_passe(monkeypatch):
    c, appels = _client(monkeypatch, cle="fc-test", firecrawl_html="<html>repli</html>")

    async def ok(url, **kw):
        appels["navigateur"] += 1
        return "<html>navigateur</html>"

    monkeypatch.setattr(c, "_render_browser", ok)
    assert await c.render("https://www.cardmarket.com/x") == "<html>navigateur</html>"
    assert appels == {"navigateur": 1, "firecrawl": 0}  # zéro crédit dépensé


@pytest.mark.asyncio
async def test_repli_quand_le_domaine_est_bloque(monkeypatch):
    c, appels = _client(monkeypatch, cle="fc-test", firecrawl_html="<html>repli</html>")

    async def bloque(url, **kw):
        raise DomainCooldownError("www.cardmarket.com", 0.0)

    monkeypatch.setattr(c, "_render_browser", bloque)
    assert await c.render("https://www.cardmarket.com/x") == "<html>repli</html>"
    assert appels["firecrawl"] == 1


@pytest.mark.asyncio
async def test_sans_repli_l_erreur_d_origine_remonte(monkeypatch):
    """Pas de clé (ou Firecrawl en panne) : on relance l'erreur, on ne l'avale pas."""
    c, _ = _client(monkeypatch, cle="", firecrawl_html=None)

    async def bloque(url, **kw):
        raise DomainCooldownError("www.cardmarket.com", 0.0)

    monkeypatch.setattr(c, "_render_browser", bloque)
    with pytest.raises(DomainCooldownError):
        await c.render("https://www.cardmarket.com/x")


@pytest.mark.asyncio
async def test_pas_de_cle_pas_d_appel_reseau(monkeypatch):
    """Sans clé, _render_firecrawl sort avant toute requête."""
    c = ScrapeClient()
    monkeypatch.setattr("bot.scrapers.base.get_settings",
                        lambda: type("S", (), {"firecrawl_api_key": ""})())
    assert await c._render_firecrawl("https://www.cardmarket.com/x") is None
    assert c._http is None  # aucun client HTTP n'a même été ouvert


# --- détection du blocage : c'est elle qui déclenche le repli ------------------
def test_403_est_un_blocage():
    assert is_blocked(status=403) is True   # pare-feu Cloudflare (« Attention Required »)
    assert is_blocked(status=429) is True   # rate-limit


def test_200_normal_n_est_pas_un_blocage():
    assert is_blocked(status=200, html="<html><body>Noctali ex 1,80 €</body></html>") is False


def test_page_de_ban_reelle_servie_en_200():
    """HTML capturé sur la vraie page de blocage Cardmarket, pas une chaîne inventée."""
    assert is_blocked(status=200, html=BLOCAGE_REEL.read_text(encoding="utf-8")) is True
