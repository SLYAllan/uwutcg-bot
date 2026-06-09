# Riftbound — League of Legends TCG (base de connaissances)

> Données alignées sur les **règles officielles FR « Règles du jeu de Riftbound »**
> (107 p., MAJ 30/03/2026) et les cartes de référence Origines. Terminologie FR officielle.
> Le calendrier des sets futurs et certaines cotes restent volatils (marqués ⚠️).
> Source de données cartes recommandée pour le bot : **API Riftcodex** (voir section dédiée).

## Présentation
- **Riftbound** est le jeu de cartes à collectionner officiel de **League of Legends**, édité par **Riot Games**.
- Univers Runeterra : champions, régions et factions de LoL.
- Déploiement initial Asie (Chine) en 2025, puis international (EN) et marché FR. (⚠️ dates/prix FR précis à confirmer.)
- Condition de victoire originale (par points, pas par « points de vie »), centrée sur le contrôle de champs de bataille.

## Les 6 Domaines (les « couleurs »)
| Domaine | EN (couleur) | Identité |
|---|---|---|
| **Furie** | Fury (rouge) | Agression, conquête rapide, dégâts directs, mot-clé Assaut |
| **Calme** | Calm (vert) | Endurance, récupération, croissance d'unités, Réaction, Embuscade |
| **Esprit** | Mind (bleu) | Contrôle, sorts, disruption, adaptation, équipements |
| **Corps** | Body (orange) | Puissance brute, haute Puissance (Might), domination au combat |
| **Chaos** | Chaos (violet) | Imprévisibilité, haut risque/récompense, combos explosifs |
| **Ordre** | Order (jaune) | Structure, protection d'unités, contrôle méthodique, Agonie, jetons |

Synergies classiques : **Furie + Corps** (agressif unités), **Esprit + Ordre** (contrôle/consistance).
La **Légende** définit les **2 domaines** jouables du deck. Débutants : Furie ou Corps (éviter Chaos au départ).

## Composition d'un deck
- **Légende** : 1 carte ; définit les 2 domaines + capacité spéciale. Dans une zone dédiée, **n'entre jamais sur le champ de bataille**.
- **Champion (élu)** : 1 unité du deck principal déclarée avant la partie (supertype Champion). 1 copie désignée obligatoire, jusqu'à 3 copies au total.
- **Cartes Signature** : jusqu'à 3, correspondant au tag de la Légende Champion.
- **Deck principal** : au minimum 40 cartes (unités, sorts, équipements) ; 40 recommandé pour la consistance.
- **Deck de runes** : exactement **12 runes**, correspondant aux domaines de la Légende.
- **Champs de bataille** : 3 (Bo1 : 1 aléatoire ; Bo3 : choix du joueur).
- **Réserve / Side Deck** : cartes d'échange entre manches en Bo3.
- **Main de départ** : 4 cartes ; mulligan possible (remettre jusqu'à 2, repiocher autant).

### Ratios de deckbuilding recommandés
Unités ≥ 20 · Sorts 8–14 · Équipements 2–6. Règle des 3 copies : carte clé = 3 exemplaires, situationnelle = 1–2.

## Condition de victoire & ressources
- **Premier à 8 points de victoire.**
- **Conquête** : avoir des unités sur un champ sans unité adverse → +1 point (max 1/champ/tour).
- **Contrôle** : commencer son tour en tenant un champ déjà conquis → +1 point par champ tenu.
- Ressources : **Énergie** (épuiser une rune, elle reste), **Puissance/Power** (recycler une rune du bon domaine), **XP** (via le mot-clé Chasse, débloque les capacités Niveau).

## Types de cartes & stats
- **Unité** (Unit) : combat sur les champs de bataille. Stat unique **Puissance (Might, M)** = attaque ET points de vie.
- **Sort** (Spell) : effet ponctuel, va à la Défausse après résolution.
- **Équipement** (Gear) : reste en jeu, survit si l'unité meurt, ré-attachable.
- **Rune** : ressource (deck de runes, 12 exactement).
- **Légende** et **Champion** : voir composition. ⚠️ Légende (type) ≠ Champion Unit (supertype) — ce sont deux choses distinctes.

## Mots-clés officiels (FR ← EN)
Accélération (Accelerate) · Caché (Hidden) · Légion (Legion) · Assaut (Assault, +Puissance en attaque) ·
Bouclier (Shield, +Puissance en défense) · Tank (subit les dégâts d'abord) · Agonie (Deathknell) ·
Protection (Deflect) · Gank (Ganking, change de champ) · Temporaire (Temporary) · Vision (Vision) ·
Embuscade (Ambush) · Chasse (Hunt, gain d'XP) · Niveau (Level, seuil d'XP) · Expert en armes (Weaponmaster) ·
Répétition (Repeat) · Équiper (Equip) · Dégainer (Quick-Draw) · Unique (Unique) · Allégeance (Allegiance).

**Timing** : seuls **Action** (jouable à tout moment) et **Réaction** (pendant un combat) sont des mots-clés de timing. ⚠️ « Atout » n'existe pas dans les règles officielles.

## Termes de jeu utiles (FR ← EN) pour la veille
Champ de bataille (Battlefield) · Combat (Showdown) · Confrontation (l'affrontement complet) ·
Puissance/Might · Énergie · Essence runique · Défausse (Trash) · Bannissement (exil) ·
Épuiser (Exhaust) · Préparer (Ready) · Recycler (Recycle) · Canaliser (Channel) · Conquérir (Conquer).

## Sets sortis
Codes officiels (préfixes de numéro de collection) :
- **OGN — Origines (Origins)** : set de lancement.
- **SFD — Spiritforged** : 2e set.
- **UNL — Unleashed** : 3e set.
(⚠️ sets suivants & calendrier FR : à mettre à jour aux annonces Riot. La base RiftboundFr référence ~1048 cartes sur OGN/SFD/UNL.)

## Decks de démarrage (pre-built, format 40 cartes)
**Jinx, Viktor, Lee Sin, Fiora, Rumble** — prêts à jouer.

## Légendes / Champions — note de désambiguïsation (importante pour la veille)
- **Master Yi = « Master Yi, Wuju Bladesman »** dans ~99,6 % des cas. « Master Yi, Wuju Master » (légende Unleashed) est quasi jamais jouée. Ne jamais confondre les deux dans les recherches/cotes : un « Master Yi » du marché = Wuju Bladesman par défaut.
- Aliases apostrophe à gérer dans les recherches : **Kha'Zix / KhaZix**, **Kai'Sa / KaiSa**, **Rek'Sai / RekSai**.

## Produits scellés (pour /sealed)
Boosters, **displays / booster boxes**, **decks de démarrage** (Jinx/Viktor/Lee Sin/Fiora/Rumble), coffrets collector, promos d'événement. Mouvement classique : hype/montée avant sortie, creux post-sortie (afflux d'ouvertures), appréciation long terme une fois hors production. Displays asiatiques souvent moins chers à l'achat → cible d'arbitrage.

## Cartes chase / collection (⚠️ cotes à vérifier au marché)
- Versions **alt art / overnumbered / signature** (champ `metadata.alternate_art` / `overnumbered` / `signature` côté Riftcodex) = les plus recherchées.
- Légendes & champions des personnages LoL populaires en alt art foil concentrent la demande.
- Promos d'événement limitées prennent de la valeur vite. Surveiller l'écart Asie↔FR/EU pour l'arbitrage.

## API Riftcodex (source de données cartes pour le bot)
- Base URL : `https://api.riftcodex.com` — **sans** préfixe `/api/`.
- Endpoints : `GET /cards` (paginé), `GET /sets` (paginé). ⚠️ `GET /cards/search?q=...` renvoie 422 → ne pas utiliser ; filtrer côté client après `/cards`.
- Pagination : `{ items[], total, page, size, pages }`.
- Objet carte : `id, name, riftbound_id, collector_number, attributes.{energy,might,power}, classification.{type,supertype,rarity,domain[]}, text.{rich,plain,flavour}, set.{set_id,label}, media.{image_url,artist}, tags[], metadata.{clean_name,alternate_art,overnumbered,signature}`.
- ⚠️ Les cartes **Legend** ont tous les `attributes` à `null`.

## Écosystème (référence concurrence/sourcing)
- Prix marché : **Cardmarket** (EUR, marché FR/EU) et TCGPlayer (USD). magicalmeta.ink agrège des prix (dont scellés). riftbound.gg = deckbuilder/collection EN.
- Site FR de référence d'Allan : **riftboundfrance.fr** (decks de tournois, tier list, base de cartes).
