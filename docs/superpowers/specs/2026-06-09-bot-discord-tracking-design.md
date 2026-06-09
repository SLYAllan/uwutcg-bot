# Design — Bot Discord « Agent de Tracking » UwUTCG

Date : 2026-06-09
Source : `prompt-bot-discord-tracking.md` (brief utilisateur, fait office de spec fonctionnelle).

## Objectif

Bot Discord conteneurisé (Docker, VPS Hetzner, 24/7) de veille marché pour UwUTCG
(revente cartes Pokémon/Riftbound + figurines anime). Surveille annonces, ventes,
prix et taux de change sur Vinted / Cardmarket / eBay, source Japon (Mercari/Yahoo via
Buyee/FromJapan), et notifie en quasi temps réel. Le bot **n'utilise pas** l'API Claude :
la knowledge base est générée au build sous forme de fichiers markdown.

## Contraintes / décisions validées

- **Périmètre V1 = brief complet** (§7 étapes 1→10 + extensions §5 rapides).
- **Mode échafaudage** : pas de secrets bot token ni de test live des scrapers au build.
  - Logique pure (pricing, FX, arbitrage, grading-ROI, parsing calc, dédup, signaux) →
    **tests unitaires exécutés réellement** (pytest).
  - Scrapers → sélecteurs/clés/patterns isolés en tête de fichier, marqués
    `# ⚠️ VÉRIFIER EN PROD`, re-capturables via Playwright MCP.
- **Secrets** dans `.env` (gitignored). eBay = keyset PRODUCTION fourni. Discord = App ID +
  Client Secret fournis ; **Bot Token manquant** (à renseigner pour que le bot se connecte).

## Stack

Python 3.11+ · discord.py 2.x (slash only, `app_commands`) · httpx + selectolax ·
playwright (chromium async) + playwright-stealth · aiosqlite · discord.ext.tasks +
APScheduler · matplotlib · rapidfuzz · pydantic-settings · PyYAML · pytest + pytest-asyncio.

## Architecture (voir §6 du brief)

```
bot/
├─ main.py            bootstrap, chargement cogs + knowledge
├─ config.py          settings (.env) + accès table config
├─ db/                aiosqlite, schéma, repositories
├─ scrapers/          base (rate-limit/retry/UA/playwright pool) + vinted/cardmarket/ebay/japan
├─ services/          fx_wise, pricing, price_monitor, arbitrage, grading_roi, signals, undervalue, knowledge
├─ cogs/              tracking, sold, monitor, calc, arbitrage, grading, sealed, knowledge, daily, config, signals
├─ ui/                discord.ui Views & Buttons (actions rapides §3.10)
├─ knowledge/         riftbound.md, pokemon.md, card_conditions.md, grading.md
├─ Dockerfile, docker-compose.yml, pyproject.toml, requirements.txt
└─ tests/             unitaires des services purs
```

Principes : requêtes sortantes centralisées dans `scrapers/base.py` (rate-limit par domaine,
jitter, retry backoff exponentiel, rotation UA, pool Playwright). Polling configurable
(défaut 5–10 min/recherche). Vues UI persistantes (`custom_id`) pour survivre aux redémarrages.

## Données (SQLite)

Tables : `tracked_searches`, `seen_listings` (dédup), `price_history`, `monitors`,
`calc_channels`, `arbitrage_watches`, `sealed_watches`, `grading_jobs`, `config`.

## Fonctionnalités (mapping brief → modules)

- §3.1 `/track` → cogs/tracking + scrapers/{vinted,cardmarket,ebay} + dédup seen_listings
- §3.2 `/sold` → cogs/sold (eBay sold scrape, Cardmarket trend, Vinted sold)
- §3.3 salon quotidien → cogs/daily + services/fx_wise (APScheduler 09:00 Europe/Paris)
- §3.4 `/monitor` Cardmarket → cogs/monitor + services/price_monitor + matplotlib graph
- §3.5 `/calc` break-even → services/pricing + cogs/calc (+ salon calc auto-parse) + pricing.yaml
- §3.6 arbitrage JP→FR → services/arbitrage + scrapers/japan + cogs/arbitrage
- §3.7 ROI grading → services/grading_roi + cogs/grading + knowledge/grading.md
- §3.8 scellé → cogs/sealed + price_history
- §3.9 détecteur de pic → services/signals
- §3.10 boutons → ui/ (lien direct + boutons bot persistants ; PAS de "payer direct")
- Knowledge → services/knowledge (rapidfuzz) + cogs/knowledge (/riftbound /pokemon /condition /grading)
- §4 utilitaires : /convert, détecteur sous-évaluation (services/undervalue)
- §5 extensions rapides : deal sniper (seuil % sous marché), heuristique anti-arnaque,
  digest hebdomadaire.

## Taux par défaut (pricing.yaml, éditables via /calc rates)

URSSAF marchandises BIC 12,3 % · versement libératoire IR 1 % · CFP 0,1 % ·
Cardmarket 5 % · eBay ~11 % + frais fixe · TikTok Shop ~5–9 % (à régler).
Assiette = CA brut encaissé (micro-entreprise, commissions non déductibles).
TVA import non récupérable (franchise) → fait partie du coût de revient.

P_min = (C + frais_fixe) / (1 − commission% − paiement% − urssaf% − impôt% − cfp%)

## Tests

Unitaires (réseau-free) : pricing (break-even + paliers), fx parsing/cache, parsing calc
(`12000 jpy ebay`, `35€ cm`, `5000¥`), arbitrage, grading_roi, signals (pic prix/volume),
dédup hash. Lancés via `pytest`.

## Hors périmètre / risques

- Pas de bouton « payer direct » (SCA/PSD2 + risque ban) — conforme brief.
- Scrapers non testés live au build (structures sites volatiles) → à valider au 1er run.
- Knowledge Riftbound : faits volatils (sets à venir, dates FR) marqués « à vérifier ».
