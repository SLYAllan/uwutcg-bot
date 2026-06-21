"""Accès base de données : connexion aiosqlite partagée + helpers + repositories.

Une seule connexion (mode WAL) suffit pour un bot solo. Toutes les requêtes passent
par cette classe ; les cogs/services reçoivent l'instance via le bot.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

import aiosqlite

from bot.db.schema import SCHEMA

log = logging.getLogger(__name__)


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        await self._migrate()
        log.info("Base de données prête : %s", self.path)

    async def _migrate(self) -> None:
        """Migrations idempotentes pour tables déjà créées en prod (ALTER non couvert
        par CREATE TABLE IF NOT EXISTS)."""
        cur = await self._conn.execute("PRAGMA table_info(monitors)")
        cols = {r[1] for r in await cur.fetchall()}
        added = []
        if "language" not in cols:
            # Langue Cardmarket (id du filtre ?language=X) ; NULL = toutes langues.
            await self._conn.execute("ALTER TABLE monitors ADD COLUMN language TEXT")
            added.append("language")
        if "threshold" not in cols:
            # Alerte seuil : ne notifie que si prix <= ce montant ; NULL = toute variation.
            await self._conn.execute("ALTER TABLE monitors ADD COLUMN threshold REAL")
            added.append("threshold")
        if "paused" not in cols:
            await self._conn.execute(
                "ALTER TABLE monitors ADD COLUMN paused INTEGER NOT NULL DEFAULT 0"
            )
            added.append("paused")
        if added:
            await self._conn.commit()
            log.info("Migration : colonnes monitors.%s ajoutées", ", monitors.".join(added))

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database non connectée : appeler connect() d'abord.")
        return self._conn

    # --- helpers génériques --------------------------------------------------
    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        cur = await self.conn.execute(sql, tuple(params))
        await self.conn.commit()
        return cur.lastrowid

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> aiosqlite.Row | None:
        cur = await self.conn.execute(sql, tuple(params))
        return await cur.fetchone()

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(sql, tuple(params))
        return list(await cur.fetchall())

    # --- table config (clé/valeur JSON) --------------------------------------
    async def config_get(self, key: str, default: Any = None) -> Any:
        row = await self.fetchone("SELECT value FROM config WHERE key = ?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    async def config_set(self, key: str, value: Any) -> None:
        await self.execute(
            "INSERT INTO config(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    async def config_all(self) -> dict[str, Any]:
        rows = await self.fetchall("SELECT key, value FROM config")
        out: dict[str, Any] = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except (json.JSONDecodeError, TypeError):
                out[r["key"]] = r["value"]
        return out

    # --- déduplication des annonces ------------------------------------------
    async def is_seen(self, search_id: int, listing_key: str) -> bool:
        row = await self.fetchone(
            "SELECT 1 FROM seen_listings WHERE search_id = ? AND listing_key = ?",
            (search_id, listing_key),
        )
        return row is not None

    async def mark_seen(self, search_id: int, listing_key: str, status: str = "new") -> int:
        """Insère l'annonce vue et renvoie son rowid (utilisé par les boutons §3.10)."""
        return await self.execute(
            "INSERT OR IGNORE INTO seen_listings(search_id, listing_key, status) VALUES(?, ?, ?)",
            (search_id, listing_key, status),
        )

    async def get_seen(self, seen_id: int) -> aiosqlite.Row | None:
        return await self.fetchone(
            "SELECT id, search_id, listing_key, status FROM seen_listings WHERE id = ?",
            (seen_id,),
        )

    async def set_seen_status_by_id(self, seen_id: int, status: str) -> None:
        await self.execute("UPDATE seen_listings SET status = ? WHERE id = ?", (status, seen_id))

    async def set_listing_status(self, search_id: int, listing_key: str, status: str) -> None:
        await self.execute(
            "UPDATE seen_listings SET status = ? WHERE search_id = ? AND listing_key = ?",
            (status, search_id, listing_key),
        )

    # --- historique de prix ---------------------------------------------------
    async def record_price(
        self,
        subject_type: str,
        subject_id: int,
        price: float,
        currency: str = "EUR",
        offers_count: int | None = None,
    ) -> None:
        await self.execute(
            "INSERT INTO price_history(subject_type, subject_id, price, currency, offers_count) "
            "VALUES(?, ?, ?, ?, ?)",
            (subject_type, subject_id, price, currency, offers_count),
        )

    async def price_series(
        self, subject_type: str, subject_id: int, days: int | None = None
    ) -> list[aiosqlite.Row]:
        sql = (
            "SELECT price, currency, offers_count, recorded_at FROM price_history "
            "WHERE subject_type = ? AND subject_id = ?"
        )
        params: list[Any] = [subject_type, subject_id]
        if days is not None:
            sql += " AND recorded_at >= datetime('now', ?)"
            params.append(f"-{days} days")
        sql += " ORDER BY recorded_at ASC"
        return await self.fetchall(sql, params)
