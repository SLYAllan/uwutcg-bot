"""Schéma SQL (DDL). Appliqué idempotemment au démarrage (CREATE TABLE IF NOT EXISTS)."""

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Recherches de tracking multi-plateforme (§3.1)
CREATE TABLE IF NOT EXISTS tracked_searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT NOT NULL,          -- vinted | cardmarket | ebay
    query        TEXT NOT NULL,
    channel_id   INTEGER,                -- salon de notif (NULL = défaut)
    max_price    REAL,                   -- filtre prix max (€)
    muted        INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Déduplication des annonces déjà vues (§3.1)
CREATE TABLE IF NOT EXISTS seen_listings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id    INTEGER NOT NULL,
    listing_key  TEXT NOT NULL,          -- id annonce ou hash URL
    status       TEXT NOT NULL DEFAULT 'new',  -- new | bought | ignored | saved
    seen_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(search_id, listing_key),
    FOREIGN KEY(search_id) REFERENCES tracked_searches(id) ON DELETE CASCADE
);

-- Historique de prix construit par le bot (§3.4, §3.8, §3.9)
CREATE TABLE IF NOT EXISTS price_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,          -- monitor | sealed | search
    subject_id   INTEGER NOT NULL,
    price        REAL NOT NULL,
    currency     TEXT NOT NULL DEFAULT 'EUR',
    offers_count INTEGER,
    recorded_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_price_history_subject
    ON price_history(subject_type, subject_id, recorded_at);

-- Monitors de prix Cardmarket détaillés (§3.4)
CREATE TABLE IF NOT EXISTS monitors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    card_name    TEXT NOT NULL,
    url          TEXT,
    channel_id   INTEGER,                -- salon dédié créé par le bot
    last_lowest  REAL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Suivi de produits scellés (§3.8)
CREATE TABLE IF NOT EXISTS sealed_watches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product      TEXT NOT NULL,
    buy_below    REAL,
    channel_id   INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Radar d'arbitrage Japon -> France (§3.6)
CREATE TABLE IF NOT EXISTS arbitrage_watches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    query        TEXT NOT NULL,
    min_margin   REAL NOT NULL DEFAULT 0.30,
    channel_id   INTEGER,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Salons "calculateur" (§3.5) avec défauts par salon
CREATE TABLE IF NOT EXISTS calc_channels (
    channel_id      INTEGER PRIMARY KEY,
    default_import   REAL DEFAULT 0,
    default_ship_in  REAL DEFAULT 0,
    default_ship_out REAL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Config clé/valeur (réglage à chaud, override de pricing.yaml)
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
