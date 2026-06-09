# UwUTCG — Bot Discord « Agent de Tracking »

Bot Discord de veille marché pour la revente de cartes (Pokémon, Riftbound) et figurines :
tracking d'annonces multi-plateforme (Vinted / Cardmarket / eBay), ventes réussies, monitoring
de prix, calculateur de rentabilité micro-entreprise, arbitrage Japon→France, ROI de grading,
suivi de scellé, détecteur de pic, et actions rapides sur les alertes. Conçu pour tourner en
**conteneur Docker 24/7** (VPS Hetzner).

> Le bot **n'utilise pas l'API Claude** : la base de connaissances (`knowledge/`) est en markdown,
> chargée au démarrage et interrogée par recherche fuzzy.

## Sommaire des commandes

| Commande | Rôle |
|---|---|
| `/track add\|list\|remove` | Suivi d'annonces Vinted/Cardmarket/eBay (§3.1) |
| `/sold platform query` | Ventes réussies : min/médian/max (§3.2) |
| `/monitor create\|list\|remove` | Salon dédié + suivi prix Cardmarket + graphique (§3.4) |
| `/calc compute` · `/calc bind\|unbind` · `/calc rates` | Seuil de rentabilité + salon auto (§3.5) |
| `/convert` | Conversion JPY↔EUR (taux Wise en cache) |
| `/arbitrage watch\|list\|remove` | Radar d'arbitrage Japon→France (§3.6) |
| `/grading-roi` | Estimateur de ROI de grading (§3.7) |
| `/sealed watch\|list\|remove` | Suivi de produits scellés (§3.8) |
| `/riftbound` `/pokemon` `/condition` `/grading` | Consultation de la knowledge base (§2) |
| `/config ...` | Salons par défaut, affichage config |

Le **salon quotidien** (taux Wise + synthèse monitoring) et le **digest hebdo** sont automatiques
(APScheduler, 09:00 Europe/Paris). Les embeds d'alerte portent des **boutons** : lien direct (panier
eBay / article Vinted / page Cardmarket), « Calcule ma marge », Acheté/Ignorer, Mute, Sauvegarder.

## Prérequis

- Docker + Docker Compose (déploiement) **ou** Python 3.11+ (dev local).
- Un **bot Discord** (token), une **clé application eBay** (API Browse, OAuth client credentials).

## Configuration — `.env`

Copier `.env.example` → `.env` et renseigner :

- `DISCORD_TOKEN` : **le Bot Token** (portail dev Discord → onglet *Bot* → *Reset Token*).
  ⚠️ Ce n'est PAS le *Client Secret*. Le bot ne se connecte qu'avec le Bot Token.
- `DISCORD_GUILD_ID` (recommandé en dev) : sync instantané des slash commands sur ton serveur.
  Sans lui, le sync est global (propagation ~1 h).
- `EBAY_APP_ID` / `EBAY_CERT_ID` : keyset **production** eBay (l'API Browse suffit, gratuite).
- `VINTED_SESSION_COOKIE` : optionnel ; sinon le bot récupère lui-même un cookie en visitant le site.

**Permissions Discord du bot** : activer l'intent *Message Content* (pour le salon calculateur),
et inviter le bot avec les scopes `bot applications.commands` + droits *Send Messages*,
*Embed Links*, *Attach Files*, *Manage Channels* (pour `/monitor create`).

### Sécurité des secrets
- `.env` est dans `.gitignore` — **ne jamais le committer**.
- Si un secret a fui (ex. collé en clair), **régénère-le** (Reset Token Discord, nouveau keyset eBay).

## Lancement

### Docker (recommandé)
```bash
docker compose up -d --build
docker compose logs -f bot
```
Volumes : `./data` (DB SQLite persistante), `./knowledge` et `./pricing.yaml` (éditables sans rebuild).

### Local (dev)
```bash
python -m venv .venv && . .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python -m bot.main
```

## Tests
```bash
pip install -r requirements.txt
pytest
```
Les tests couvrent toute la **logique pure** : calculateur (point mort/paliers), parsing du salon
calculateur, arbitrage, ROI grading, détecteur de pic, sous-évaluation, FX, knowledge, tendances.
Les scrapers (réseau) ne sont pas testés automatiquement (voir ci-dessous).

## Réglage des taux (`pricing.yaml`)
Charges micro-entreprise (URSSAF 12,3 %, IR 1 %, CFP 0,1 %), commissions par plateforme,
coûts de sourcing Japon et de grading, seuils d'alerte. Éditer le fichier (monté en volume)
puis redémarrer le conteneur, ou consulter via `/calc rates`. La table `config` permet aussi
des overrides à chaud (clé `pricing_overrides`).

## Ajouter / corriger un scraper

Tous les scrapers passent par `bot/scrapers/base.py` (`ScrapeClient`) qui gère rate-limit par
domaine, jitter, retry/backoff et le pool Playwright. Pour ajouter une plateforme :

1. Créer `bot/scrapers/ma_plateforme.py` avec une classe recevant `ScrapeClient`.
2. **Regrouper les sélecteurs / clés JSON / patterns d'URL en tête de fichier** (constante
   `*_SELECTORS` / `*_KEYS`) — ils sont volatils.
3. Renvoyer des objets `Listing` (et `SoldStats` pour les ventes).
4. Brancher dans le cog concerné.

> ⚠️ **Scrapers non testés en live au build.** Les structures de Vinted (endpoint JSON interne),
> Cardmarket (HTML derrière Cloudflare), eBay (pages *sold*) et Buyee changent régulièrement.
> Avant la prod, **re-capturer les sélecteurs/URLs avec Playwright MCP** et corriger les blocs
> `# ⚠️ VÉRIFIER EN PROD`. L'API Browse eBay (annonces actives) est la voie la plus stable.

### eBay watchlist (bouton ➕)
L'ajout à la watchlist eBay nécessite un **token utilisateur** (OAuth *Authorization Code*),
en plus de la clé application. À configurer via le flow de consentement eBay (non inclus :
le bot n'a aujourd'hui que le client-credentials pour l'API Browse). Le bouton explique cette limite.

## Architecture
```
bot/
├─ main.py            bootstrap (DI : DB, scrapers, services, scheduler, cogs)
├─ config.py          .env (Settings) + pricing.yaml + table config
├─ db/                schéma SQLite + accès aiosqlite + dédup + price_history
├─ scrapers/          base (anti-ban) + vinted / cardmarket / ebay / japan
├─ services/          pricing, fx_wise, arbitrage, grading_roi, signals,
│                     undervalue, price_monitor, knowledge
├─ cogs/              tracking, sold, monitor, calc, arbitrage, grading,
│                     sealed, knowledge, signals, daily, config
├─ ui/                embeds + boutons d'action persistants (§3.10)
└─ knowledge/         riftbound.md, pokemon.md, card_conditions.md, grading.md
```

## Limites assumées
- Pas de bouton « payer direct » : l'authentification forte (SCA/PSD2) impose ta validation, et
  automatiser le checkout Vinted ferait courir un risque de bannissement. Le bouton lien t'amène
  au plus près du paiement (panier eBay / écran d'achat Vinted), la validation reste de ton côté.
- Ce calculateur est une aide à la décision, pas un avis comptable (taux paramétrables).
