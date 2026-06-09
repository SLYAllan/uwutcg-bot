"""Client de la base de cartes Riftbound (API Riftcodex).

Source de données cartes pour la commande /carte. API publique, pas de clé.
- Base : https://api.riftcodex.com (PAS de préfixe /api/)
- GET /cards (paginé), GET /sets (paginé)
- ⚠️ GET /cards/search?q=... renvoie 422 → on charge tout /cards et on filtre côté client.
- Pagination : { items[], total, page, size, pages }
- Les cartes Legend ont tous les `attributes` à null.

La recherche fuzzy par nom est isolée dans `rank_cards` (pure → testable).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from bot.scrapers.base import ScrapeClient

log = logging.getLogger(__name__)

RIFTCODEX_BASE = "https://api.riftcodex.com"
PAGE_SIZE = 100


@dataclass
class Card:
    id: str
    name: str
    riftbound_id: str | None
    collector_number: str | None
    energy: int | None
    might: int | None
    power: int | None
    type: str | None
    supertype: str | None
    rarity: str | None
    domains: list[str] = field(default_factory=list)
    text_plain: str = ""
    flavour: str = ""
    set_id: str | None = None
    set_label: str | None = None
    image_url: str | None = None
    artist: str | None = None
    tags: list[str] = field(default_factory=list)
    alternate_art: bool = False
    overnumbered: bool = False
    signature: bool = False

    @property
    def is_legend(self) -> bool:
        return (self.supertype or "").lower() == "legend" or (self.type or "").lower() == "legend"


def parse_card(d: dict) -> Card:
    attr = d.get("attributes") or {}
    cls = d.get("classification") or {}
    txt = d.get("text") or {}
    st = d.get("set") or {}
    media = d.get("media") or {}
    meta = d.get("metadata") or {}
    return Card(
        id=str(d.get("id", "")),
        name=d.get("name", "(sans nom)"),
        riftbound_id=d.get("riftbound_id"),
        collector_number=d.get("collector_number"),
        energy=attr.get("energy"),
        might=attr.get("might"),
        power=attr.get("power"),
        type=cls.get("type"),
        supertype=cls.get("supertype"),
        rarity=cls.get("rarity"),
        domains=cls.get("domain") or [],
        text_plain=(txt.get("plain") or "").strip(),
        flavour=(txt.get("flavour") or "").strip(),
        set_id=st.get("set_id"),
        set_label=st.get("label"),
        image_url=media.get("image_url"),
        artist=media.get("artist"),
        tags=d.get("tags") or [],
        alternate_art=bool(meta.get("alternate_art")),
        overnumbered=bool(meta.get("overnumbered")),
        signature=bool(meta.get("signature")),
    )


def rank_cards(cards: list[Card], term: str, limit: int = 5) -> list[Card]:
    """Classe les cartes par pertinence de nom (fuzzy). Pure → testable."""
    t = term.lower().strip()
    scored: list[tuple[float, Card]] = []
    for c in cards:
        name = c.name.lower()
        # bonus fort si le terme est un préfixe / sous-chaîne exacte du nom
        exact = 100 if t == name else (90 if t in name else 0)
        score = max(exact, fuzz.WRatio(t, name))
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:limit]]


class RiftcodexScraper:
    def __init__(self, client: ScrapeClient):
        self.client = client
        self._cards: list[Card] = []
        self._loaded = False

    async def ensure_loaded(self, force: bool = False) -> None:
        if self._loaded and not force:
            return
        cards: list[Card] = []
        page = 1
        while True:
            data = await self.client.get_json(
                f"{RIFTCODEX_BASE}/cards",
                params={"page": str(page), "size": str(PAGE_SIZE)},
                min_interval=1.0,
            )
            items = data.get("items", []) or []
            cards.extend(parse_card(it) for it in items)
            pages = int(data.get("pages", 1) or 1)
            if page >= pages or not items:
                break
            page += 1
        self._cards = cards
        self._loaded = True
        log.info("Riftcodex : %d cartes chargées (%d pages)", len(cards), page)

    async def search(self, term: str, limit: int = 5) -> list[Card]:
        await self.ensure_loaded()
        return rank_cards(self._cards, term, limit)

    @property
    def count(self) -> int:
        return len(self._cards)
