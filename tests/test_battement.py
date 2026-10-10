import asyncio
import http.server
import threading

import pytest

from bot import battement


class _Dashboard(http.server.BaseHTTPRequestHandler):
    recus: list[tuple[str, str | None]] = []
    code = 204

    def do_POST(self):  # noqa: N802
        _Dashboard.recus.append((self.path, self.headers.get("Authorization")))
        self.send_response(_Dashboard.code)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def dashboard():
    _Dashboard.recus = []
    _Dashboard.code = 204
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Dashboard)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_envoyer_poste_avec_le_jeton_en_bearer(dashboard):
    assert battement.envoyer(f"{dashboard}/api/battement/uwutcg-bot", "secret") == 204
    assert _Dashboard.recus == [("/api/battement/uwutcg-bot", "Bearer secret")]


def test_un_refus_n_arrete_pas_la_boucle(dashboard):
    _Dashboard.code = 401

    async def tours():
        tache = asyncio.create_task(battement.boucle(f"{dashboard}/b", "x", periode=0.05))
        await asyncio.sleep(0.3)
        assert not tache.done()
        tache.cancel()

    asyncio.run(tours())
    assert len(_Dashboard.recus) >= 2


def test_sans_variable_la_boucle_rend_la_main_et_le_dit(caplog):
    asyncio.run(battement.boucle("", "x"))
    assert "Battement coupé" in caplog.text
