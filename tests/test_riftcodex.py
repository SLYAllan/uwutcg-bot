from bot.scrapers.riftcodex import Card, parse_card, rank_cards


def _card(name, **kw):
    return Card(id=name, name=name, riftbound_id=None, collector_number=None,
               energy=None, might=None, power=None, type=None, supertype=None,
               rarity=None, **kw)


def test_parse_card_full():
    d = {
        "id": "abc", "name": "Jinx", "riftbound_id": "OGN-001",
        "collector_number": "OGN-001",
        "attributes": {"energy": 3, "might": 4, "power": 2},
        "classification": {"type": "Unit", "supertype": "Champion", "rarity": "Epic",
                            "domain": ["Fury"]},
        "text": {"plain": "Boom", "flavour": "..."},
        "set": {"set_id": "OGN", "label": "Origines"},
        "media": {"image_url": "http://img", "artist": "X"},
        "tags": ["jinx"], "metadata": {"alternate_art": True, "signature": False},
    }
    c = parse_card(d)
    assert c.name == "Jinx" and c.might == 4 and c.domains == ["Fury"]
    assert c.set_label == "Origines" and c.alternate_art is True


def test_parse_card_legend_null_attributes():
    d = {"id": "l", "name": "Master Yi, Wuju Bladesman",
         "attributes": None, "classification": {"supertype": "Legend"}}
    c = parse_card(d)
    assert c.is_legend is True
    assert c.energy is None and c.might is None


def test_rank_cards_exact_and_substring():
    cards = [_card("Jinx"), _card("Jinx, Loose Cannon"), _card("Viktor"), _card("Lee Sin")]
    res = rank_cards(cards, "jinx", limit=3)
    assert res[0].name == "Jinx"           # exact match en tête
    assert "Viktor" not in [c.name for c in res[:2]]


def test_rank_cards_fuzzy_typo():
    cards = [_card("Viktor"), _card("Jinx"), _card("Fiora")]
    res = rank_cards(cards, "viktr", limit=1)
    assert res[0].name == "Viktor"
