"""Battement vers le Dashboard du serveur maison (annexe A.3, U3).

Chaque minute, POST <url> avec le jeton du projet. Le Dashboard alerte sur Discord quand
le battement manque depuis 3 minutes. Une erreur ici n'arrête jamais le bot : elle est
écrite au journal, et l'alerte du Dashboard dit le reste.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.request

log = logging.getLogger(__name__)


def envoyer(url: str, jeton: str, delai: float = 10) -> int:
    requete = urllib.request.Request(url, method="POST", headers={"Authorization": f"Bearer {jeton}"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return reponse.status


async def boucle(url: str, jeton: str, periode: float = 60) -> None:
    if not url or not jeton:
        # Lancé en local, ou avant que les variables soient posées : le bot doit tourner
        # quand même ; l'absence de battement déclenche l'alerte du Dashboard.
        log.warning("Battement coupé : DASHBOARD_BATTEMENT_URL ou DASHBOARD_BATTEMENT_JETON absente")
        return
    while True:
        try:
            await asyncio.to_thread(envoyer, url, jeton)
        except Exception as e:  # noqa: BLE001 : réseau coupé, Dashboard arrêté, jeton refusé
            log.warning("Battement refusé : %s", e)
        await asyncio.sleep(periode)
