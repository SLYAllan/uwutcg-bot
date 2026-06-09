"""Base de connaissances locale (§2). Le bot N'UTILISE PAS l'API Claude.

Charge les fichiers markdown de knowledge/ en mémoire au démarrage, les découpe par
section (titres `##`), et répond par recherche de mots-clés + fuzzy matching (rapidfuzz).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)


@dataclass
class Section:
    title: str
    body: str
    source: str          # nom du fichier (ex. "riftbound")

    @property
    def haystack(self) -> str:
        return f"{self.title}\n{self.body}"


def split_sections(text: str, source: str) -> list[Section]:
    """Découpe un markdown par titres `##` (et `#`). Le préambule devient une section."""
    sections: list[Section] = []
    current_title = "Introduction"
    current_lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^#{1,3}\s+(.*)$", line)
        if m:
            if current_lines:
                sections.append(
                    Section(current_title, "\n".join(current_lines).strip(), source)
                )
            current_title = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append(Section(current_title, "\n".join(current_lines).strip(), source))
    return [s for s in sections if s.body or s.title]


class KnowledgeBase:
    """Un fichier .md = un domaine. Recherche fuzzy sur titres + corps de section."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.docs: dict[str, list[Section]] = {}

    def load(self) -> None:
        self.docs.clear()
        if not self.directory.exists():
            log.warning("Dossier knowledge introuvable : %s", self.directory)
            return
        for md in sorted(self.directory.glob("*.md")):
            name = md.stem
            self.docs[name] = split_sections(md.read_text(encoding="utf-8"), name)
            log.info("Knowledge '%s' chargé (%d sections)", name, len(self.docs[name]))

    def search(self, doc: str, term: str, limit: int = 3) -> list[Section]:
        """Sections les plus pertinentes d'un doc pour `term` (fuzzy sur titre+corps)."""
        sections = self.docs.get(doc, [])
        if not sections:
            return []
        # Priorité au match de titre, puis au corps.
        scored: list[tuple[float, Section]] = []
        for s in sections:
            title_score = fuzz.partial_ratio(term.lower(), s.title.lower())
            body_score = fuzz.partial_ratio(term.lower(), s.body.lower())
            scored.append((title_score * 1.5 + body_score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    def best_section(self, doc: str, term: str) -> Section | None:
        res = self.search(doc, term, limit=1)
        return res[0] if res else None

    def list_section_titles(self, doc: str) -> list[str]:
        return [s.title for s in self.docs.get(doc, [])]
