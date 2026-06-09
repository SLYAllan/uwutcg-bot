# Prompt Claude Code — Bot Discord « Agent de Tracking » UwUTCG

> Copie-colle l'intégralité de ce document dans Claude Code comme brief de projet.

---

## 0. Contexte

Je m'appelle Allan, je gère **UwUTCG**, une activité de revente de cartes à collectionner (Pokémon, Riftbound) et de figurines anime (Banpresto, Ichiban Kuji, SEGA SPM), sous statut **micro-entrepreneur en franchise de TVA** (la TVA à l'import n'est PAS récupérable — important pour tout calcul de marge). Je vends sur Vinted, Cardmarket, eBay et TikTok Shop, et je source au Japon (Mercari JP, Yahoo Auctions) via Buyee / FromJapan.

Je veux un **bot Discord** qui centralise toute ma veille marché : un « agent de tracking » qui surveille les annonces, les ventes, les prix et les taux de change, et qui me notifie en temps quasi réel.

Je suis à l'aise techniquement : je tourne sur un **VPS Hetzner avec Docker**. Le bot doit être conçu pour tourner en conteneur Docker sur ce VPS, 24/7.

---

## ⚙️ Environnement Claude Code recommandé (à activer avant de coder)

Configure ces extensions Claude Code dès le départ — elles sont pensées pour ce projet :

- **Playwright MCP** (serveur officiel Microsoft) — le plus important. Donne à Claude Code un vrai navigateur avec accès au DOM et aux requêtes réseau : sert à **inspecter Vinted/Cardmarket/eBay en live**, repérer l'endpoint JSON interne de Vinted dans l'onglet réseau, tester les sélecteurs Cardmarket derrière Cloudflare, et valider chaque scraper de façon itérative plutôt qu'à l'aveugle.
  `claude mcp add playwright -- npx @playwright/mcp@latest` (vérifie la syntaxe exacte dans la doc Claude Code)
- **Marketplace de plugins officielle Anthropic** — `/plugin marketplace add anthropics/claude-plugins-official`, puis `/plugin` pour installer. Collections utiles ici : **software-engineering** (revue de code, debug, documentation) et **devops-infrastructure** (Docker, CI/CD) pour le déploiement Hetzner et la qualité du code.
- **GitHub MCP** (optionnel) — piloter le repo (issues, PR, commits) directement depuis Claude Code.

> ⚠️ Sécurité : ce bot manipule des secrets sensibles (token Discord, token/cookies Vinted, clés API). Un plugin tiers s'exécute avec les droits de Claude Code sur la machine — n'installe que des sources officielles/réputées, garde les secrets dans `.env` (jamais en dur) et ajoute `.env` au `.gitignore`.

---

## 1. Stack technique imposée

- **Langage** : Python 3.11+
- **Lib Discord** : `discord.py` 2.x — **slash commands** (`app_commands`) obligatoires, pas de commandes préfixées.
- **Scraping** :
  - `httpx` (async) + `selectolax` ou `BeautifulSoup` pour les pages statiques / endpoints JSON.
  - **`playwright`** (chromium, mode async) pour tout ce qui est protégé (Cloudflare, JS lourd) — **Cardmarket en a besoin**. Prévoir un user-agent réaliste, des délais aléatoires, et idéalement `playwright-stealth`.
- **Base de données** : **SQLite** via `aiosqlite` (fichier unique, parfait pour un VPS solo). Tables minimum : `tracked_searches`, `seen_listings` (déduplication), `price_history`, `monitors`, `calc_channels`, `config`.
- **Scheduling** : `discord.ext.tasks` (boucles de polling) + `APScheduler` pour les jobs cron quotidiens (taux de change, digest).
- **Config** : fichier `.env` (token Discord, IDs de salons, secrets) + table `config` en base pour le réglage à chaud via commandes.
- **Déploiement** : `Dockerfile` + `docker-compose.yml`. Volume persistant pour la base SQLite et le dossier `knowledge/`. Logs structurés.

**Important — robustesse anti-ban** : centralise toutes les requêtes sortantes dans un module `scrapers/base.py` qui gère : rotation de user-agents, délais aléatoires (jitter), retry avec backoff exponentiel, et un rate-limiter par domaine. Aucune plateforme ne doit être interrogée plus souvent que nécessaire (polling configurable, défaut : toutes les 5–10 min par recherche).

> ⚠️ Les endpoints internes (Vinted notamment) et le HTML (Cardmarket, eBay) **changent régulièrement**. Avant d'écrire les scrapers, vérifie toi-même la structure actuelle des pages/réponses, et conçois chaque scraper de façon isolée et facile à corriger (sélecteurs/clés JSON regroupés en haut de chaque fichier).

---

## 2. Base de connaissances (`knowledge/`)

**Le bot N'UTILISE PAS l'API Claude.** À la place, **toi, Claude Code, tu génères au moment du build des fichiers markdown contenant TES connaissances**, que le bot charge en mémoire au démarrage et interroge par recherche de mots-clés / fuzzy search (`rapidfuzz`).

Crée et remplis ces fichiers avec un maximum de détail :

- **`knowledge/riftbound.md`** — Tu es censé bien connaître Riftbound (le TCG Riot Games / univers League of Legends). Dump tout : factions/domaines, types de cartes, système de jeu, raretés, liste des sets sortis et à venir, cartes clés et chase cards, terminologie FR/EN, infos sur le lancement FR. Sois exhaustif.
- **`knowledge/pokemon.md`** — Sets et ères (WotC, EX, DP, dont **LV.X**, BW, XY, SM, SWSH, SV…), différences sets JP vs EN/FR, cartes et raretés recherchées, terminologie de collection.
- **`knowledge/card_conditions.md`** — **L'échelle de conditions Cardmarket** précisément : Mint (M), Near Mint (NM), Excellent (EX), Good (GD), Light Played (LP), Played (PL), Poor (PO) — avec définition de chaque état. Ajoute les équivalences courantes FR/EN.
- **`knowledge/grading.md`** — Les sociétés de grading et leurs échelles :
  - **PSA** (1–10, dont PSA 10 Gem Mint)
  - **BGS / Beckett** (1–10, demi-points, sous-notes centering/corners/edges/surface, Black Label)
  - **CGC** (1–10, Pristine 10)
  - **PCA** (société française, échelle 1–10)
  - Mentionne aussi les autres si pertinent. Explique l'impact du grade sur la valeur.

Le bot expose des **slash commands de consultation** qui lisent ces fichiers :
- `/riftbound <terme>` — réponse depuis `riftbound.md`
- `/pokemon <terme>` — réponse depuis `pokemon.md`
- `/condition <état>` — explique un état de carte (depuis `card_conditions.md`)
- `/grading <société>` — explique une échelle de grading (depuis `grading.md`)

Structure les `.md` avec des titres clairs (`##`) pour que la recherche par section soit fiable.

---

## 3. Fonctionnalités principales

### 3.1 Tracking d'annonces multi-plateforme

Commandes :
- `/track add platform:<vinted|cardmarket|ebay> query:"<terme>" [channel:<#salon>] [max_price:<€>]`
- `/track list`
- `/track remove id:<id>`

Comportement : pour chaque recherche enregistrée, le bot poll périodiquement, **déduplique** via `seen_listings` (clé = id annonce ou hash URL), et **poste un embed Discord pour CHAQUE nouvelle annonce** dans le salon choisi (ou un salon par défaut). L'embed contient : titre, prix, devise, état/condition si dispo, vendeur, plateforme, miniature image, et lien direct.

Spécificités par plateforme :
- **Vinted** : pas d'API publique. Utilise l'endpoint JSON interne du catalogue (`/api/v2/catalog/items`) — il faut d'abord récupérer le cookie/token d'accès en visitant le site, puis le réutiliser et le rafraîchir. Gère l'expiration du token.
- **Cardmarket** : scraping via Playwright (Cloudflare). Parse les pages de résultats de recherche produit.
- **eBay** : pour les annonces **actives**, l'**API Browse officielle** est gratuite et simple (OAuth application token) — **privilégie-la**. Filtre sur eBay France si possible.

### 3.2 Ventes réussies

- `/sold platform:<ebay|cardmarket|vinted> query:"<terme>"`

Renvoie les dernières ventes conclues trouvables, avec prix et date :
- **eBay** : l'API officielle pour les *sold listings* (Marketplace Insights) demande une approbation difficile à obtenir → **scrape les pages « sold/completed items »** (filtre `LH_Sold=1&LH_Complete=1`). C'est la voie pragmatique.
- **Cardmarket** : récupère l'historique de ventes / tendance de prix de la page produit.
- **Vinted** : récupère les articles marqués vendus si accessible.

Présente un résumé : prix min / médian / max, et la liste des dernières ventes.

### 3.3 Salon quotidien automatique

Un salon dédié (configurable) où le bot **auto-publie chaque jour** (heure configurable, défaut 09:00 Europe/Paris) :
1. **Le taux de change JPY → EUR de Wise.com.** Récupère le taux depuis la source publique de Wise (l'endpoint qui alimente leur widget de taux). Si Wise est inaccessible, fallback sur une API FX gratuite **clairement étiquetée comme fallback**, en indiquant la source dans le message.
2. **Un résumé de monitoring de prix** : la synthèse des cartes/produits que je surveille (voir §3.4) — variations notables depuis la veille.

### 3.4 Monitoring de prix détaillé d'une carte Cardmarket

- `/monitor create card:"<nom carte / URL Cardmarket>"`

Le bot **crée un salon dédié** à cette carte et y publie un **suivi détaillé**, mis à jour périodiquement :
- prix le plus bas actuel,
- nombre d'offres disponibles,
- répartition par **état** (NM, EX…) et par **langue**,
- distinction **gradées vs raw**,
- **historique de prix construit par le bot** (chaque polling enregistre un point dans `price_history`),
- tendance 7j / 30j calculée à partir de cet historique,
- idéalement un **graphique** (matplotlib → image postée dans l'embed).

Commandes liées : `/monitor list`, `/monitor remove`. Ces monitors alimentent le résumé quotidien (§3.3).

### 3.5 Calculateur d'achat & seuil de rentabilité

`/calc value:<montant> currency:<jpy|eur> [platform:<ebay|cardmarket|tiktok|all>] [shipping_in:<€>] [import:<€>] [shipping_out:<€>]`

Objectif : à partir d'une valeur d'achat (en yen ou en euro), trouver le **prix de vente de rentabilité minimal sur chaque plateforme** (eBay, Cardmarket, TikTok Shop) après toutes les ponctions, puis proposer des paliers de rentabilité.

Logique :
1. Convertit la valeur d'achat en € (taux Wise en cache si `jpy`).
2. **Coût de revient** `C` = achat + frais d'import (TVA import **non récupérable** en franchise de TVA → fait partie du coût) + port entrant + port sortant éventuel.
3. Pour **chaque plateforme**, applique :
   - commission plateforme (%),
   - frais fixe par vente (€),
   - frais de paiement (%),
   - **charges sur le CA brut** : URSSAF vente de marchandises BIC + versement libératoire de l'IR (+ CFP).
4. **Prix de rentabilité minimal** (point mort, bénéfice net = 0) :
   ```
   P_min = (C + frais_fixe) / (1 − commission% − paiement% − urssaf% − impôt% − cfp%)
   ```
5. Affiche un **tableau comparatif des 3 plateformes** : `P_min` sur chacune, en **surlignant la moins-disante** (celle où tu dois vendre le moins cher pour être rentable).
6. Pour chaque plateforme, donne les paliers **+10 % / +20 % / +30 %** au-dessus de `P_min` : prix de vente affiché, **bénéfice net en €** et **marge nette en %** correspondants.

**Taux par défaut** (vérifiés pour 2026, à garder éditables) — stockés dans une table `config` modifiable via `/calc rates` ou un fichier `pricing.yaml` :
- URSSAF vente de marchandises BIC : **12,3 %** du CA
- Versement libératoire IR (vente) : **1 %** du CA
- CFP (vente de marchandises) : **0,1 %** du CA
- Cardmarket : commission **5 %**
- eBay : **~11 % + frais fixe** (variable selon catégorie/statut vendeur — à régler par toi)
- TikTok Shop : commission **à régler** (≈ 5–9 % selon la période)

> Note d'assiette : en micro-entreprise, URSSAF et impôt se calculent sur le **CA brut encaissé**, sans déduction des charges (les commissions plateforme ne sont **pas** déductibles). Le traitement exact (notamment commission vs montant payé par l'acheteur) dépend de ta compta — d'où des taux entièrement paramétrables. Ce calculateur est une aide à la décision, pas un avis comptable.

**Assignation à un salon** : `/calc bind [channel]` marque un salon comme « salon calculateur ». Dans ce salon, tu écris simplement une valeur et le bot répond automatiquement avec le tableau complet :
- `12000 jpy ebay` → break-even + paliers sur eBay
- `35€ cm` → sur Cardmarket
- `5000¥` → comparatif des 3 plateformes (aucune précisée)

Parsing tolérant : devise reconnue via `¥ / yen / jpy / jp` et `€ / eur / euro` ; plateforme via mot-clé (`ebay`, `cm`/`cardmarket`, `tiktok`/`tts`). `/calc unbind` pour retirer l'assignation. Stocke les salons liés dans une table `calc_channels` (avec d'éventuels défauts par salon : import inclus, port sortant type, etc.).

### 3.6 Radar d'arbitrage Japon → France

Le module qui transforme la veille en achats rentables. Pour une carte ou une figurine donnée :
- Récupère le prix de sourcing au Japon (Mercari JP / Yahoo Auctions, via les pages publiques ou un proxy type Buyee/FromJapan) et calcule le **coût d'achat tout compris en €** : prix + commission proxy + port international + frais d'import (TVA non récupérable).
- Récupère le **prix de revente FR de référence** : médiane des ventes récentes (tendance Cardmarket / eBay sold, via §3.2).
- Passe le tout dans `services/pricing.py` (§3.5) pour obtenir la **marge nette estimée** par plateforme de revente.
- **Alerte** quand une opportunité dépasse un seuil de marge configurable (ex. ≥ 30 %), avec le détail du calcul.

Commandes : `/arbitrage watch query:"<terme>" [min_margin:<%>]`, `/arbitrage list`, `/arbitrage remove`. Polling périodique comme le tracking (§3.1). C'est le « deal sniper » version sourcing Japon — la fonctionnalité la plus rentable du bot.

### 3.7 Estimateur de ROI de grading

`/grading-roi card:"<nom / URL>" [company:<psa|cgc|bgs|pca>] [grade:<note visée>]`

- Compare le prix **raw** actuel au prix **gradé** (ventes sold gradées vs raw, par société et par note).
- Déduit les **coûts de grading** : tarif société + port aller-retour + assurance (table éditable dans `config`).
- Sort la **plus-value nette estimée** et le **point mort** (à partir de quelle note ça devient rentable), idéalement avec une fourchette selon la note obtenue.
- S'appuie sur la knowledge base `grading.md` pour les échelles. (Reprend la logique de ton simulateur CollectAura.)

### 3.8 Suivi de produits scellés (Riftbound & Pokémon)

Comme `/monitor` (§3.4) mais orienté **scellé** (displays, ETB, coffrets, cases) :
- suit le prix dans le temps (alimente `price_history`),
- distingue **pré-sortie vs post-sortie** et repère le mouvement classique (montée avant la sortie, creux après),
- **alerte sous un seuil d'achat** que tu définis.

Commandes : `/sealed watch product:"<nom>" [buy_below:<€>]`, `/sealed list`, `/sealed remove`. Croise avec la knowledge base Riftbound/Pokémon pour reconnaître les noms de sets/produits.

### 3.9 Détecteur de pic / vélocité

Surveille les **variations brutales** sur les cartes/produits suivis :
- pic de **prix** (ex. +X % sur la médiane en 7 jours),
- pic de **volume** d'annonces ou de ventes (intérêt soudain),
- alerte avec le contexte (avant/après, ampleur).

Utile pour anticiper un shift de méta Riftbound ou un set Pokémon qui chauffe. S'appuie sur l'historique construit par le bot (`price_history`) + un compteur de volume par recherche. Seuils configurables.

### 3.10 Actions rapides sur les alertes (boutons Discord)

Chaque embed d'alerte (§3.1 tracking, §3.6 arbitrage) porte des **boutons d'action** pour agir en un tap, sans recherche ni copier-coller. Implémente-les avec `discord.ui.View` + `Button` ; vues **persistantes** (`custom_id`) pour qu'elles survivent à un redémarrage du bot.

**1. Bouton lien direct — c'est ça, la vitesse, et ça répond exactement à la demande : un bouton `ButtonStyle.link` ouvre une vraie page web dans le navigateur / l'app, PAS dans Discord.** Le but : aller **aussi loin que la plateforme l'autorise** vers le paiement, pour qu'il ne reste qu'à confirmer. C'est une simple navigation déclenchée par toi → **aucune automatisation, aucun risque de compte** (rien à voir avec un bot qui ferait le checkout à ta place).

Cible la plus profonde possible, par plateforme :
- **eBay (le mieux)** : construis le lien d'**ajout au panier / checkout** pour les articles à prix fixe (Buy It Now). Pattern à viser : `https://cart.payments.ebay.fr/sc/add?item=<itemId>&quantity=1` (sur le bon domaine eBay de l'annonce). Tu atterris **dans le panier, à un tap du paiement**. Les enchères pures ne sont pas éligibles au panier → pour elles, lien vers l'annonce.
- **Vinted** : pas de panier ni d'URL de checkout publique (la méthode de paiement se choisit *après* le clic sur « Acheter »). La cible la plus rapide fiable = l'**URL de l'article** (`https://www.vinted.fr/items/<id>`), qui ouvre l'app déjà connecté, bouton **Acheter** visible → un tap vers le checkout. Comme l'article part au premier qui paie, c'est le bon compromis.
- **Cardmarket** : page de l'offre/produit (l'ajout au panier passe par un POST authentifié derrière Cloudflare, pas par un lien propre).

> Les URL exactes de panier/checkout (eBay) et le format d'item (Vinted) **changent** : fais **capturer le lien réel par Playwright MCP** (cliquer « Ajouter au panier »/« Acheter » sur un exemple et relever l'URL obtenue) plutôt que de coder un format en dur.

**2. Boutons côté bot (interaction) — tous faisables et utiles :**
- 💶 **Calcule ma marge** : relance `services/pricing.py` (§3.5) sur le prix exact de cette annonce et répond avec le break-even + la marge par plateforme. Pour décider en 2 secondes.
- ✅ **Acheté** / 🚫 **Ignorer** : marque le deal comme traité (stoppe les ré-alertes via `seen_listings`, log dans le digest quotidien).
- 🔕 **Mute cette recherche** / 📌 **Sauvegarder** dans une watchlist.
- ➕ **Ajouter à la watchlist eBay** : action propre via l'**API officielle eBay** (autorisée).

**⚠️ Limite importante — un bouton « payer direct » n'est pas réalisable, pour deux raisons :**
- **La loi (UE)** : tout paiement par carte exige une **authentification forte (SCA / 3-D Secure, PSD2)** que tu dois confirmer toi-même sur ton appareil. Un bot ne peut pas finaliser un paiement à ta place — il n'existe aucun moyen propre de contourner cette étape.
- **Le risque compte/sécurité** : Vinted n'a pas d'API d'achat publique ; automatiser le checkout via ses endpoints internes te ferait courir un **risque de bannissement du compte dont dépend UwUTCG**, et n'importe qui ayant accès au salon pourrait déclencher des achats. À éviter.

Le bon compromis vitesse/sécurité est donc : **bouton lien → app en un tap** pour l'ouverture instantanée, et la validation finale du paiement reste de ton côté (comme l'exige la loi). *(Option avancée, à tes risques : un bouton qui, via ta propre session, pré-charge l'écran d'achat ou envoie une offre — étapes hors paiement uniquement. Dis-le-moi si tu veux que je le détaille.)*

---

## 4. Outils utilitaires à développer en parallèle

Développe ces modules réutilisables (utilisables en interne ET exposés en commandes) :

- **Calculateur de rentabilité** : voir §3.5 (le module de calcul `services/pricing.py` y est décrit en détail — réutilise-le partout).
- **Convertisseur de devise** `/convert` : conversion JPY↔EUR (réutilise le taux Wise mis en cache).
- **Détecteur de sous-évaluation** : module qui compare le prix d'une annonce au prix marché (tendance Cardmarket / médiane des ventes eBay) et calcule l'écart en %.
- **Scraper générique en markdown** : si utile, réutilise/adapte le scraper markdown que tu as déjà développé pour ingérer une page produit en texte propre.

---

## 5. Idées d'extensions « être à l'affût » (implémente celles qui sont rapides, propose le reste)

- **Deal sniper** : alerte quand une nouvelle annonce est ≥ X % sous le prix marché (seuil configurable par recherche). Le vrai intérêt d'un agent de veille.
- **Alertes restock** sur le retail FR (style « Pokémonitor »).
- **Tracking des nouvelles sorties / précommandes** Riftbound & Pokémon.
- **Enchères qui se terminent bientôt** (eBay / Yahoo Auctions via Buyee) → rappel X h avant la fin.
- **Suivi de vendeurs JP** fiables (watchlist de boutiques Mercari/Yahoo).
- **Heuristique anti-arnaque** : flag les annonces au prix anormalement bas (souvent fake/scam).
- **Digest hebdomadaire** : récap des deals ratés/saisis, évolution des cotes suivies.
- **Watchlist groupée** : notifications regroupées plutôt qu'un message par annonce, en option par recherche.

---

## 6. Architecture & livrables attendus

```
bot/
├─ main.py                  # bootstrap, chargement cogs + knowledge
├─ config.py / .env
├─ db/                      # aiosqlite, migrations, modèles
├─ scrapers/
│  ├─ base.py               # rate-limit, retry, UA rotation, playwright pool
│  ├─ vinted.py
│  ├─ cardmarket.py
│  └─ ebay.py
├─ services/
│  ├─ fx_wise.py            # taux JPY->EUR + cache
│  ├─ pricing.py            # break-even + paliers par plateforme (§3.5)
│  ├─ price_monitor.py
│  ├─ arbitrage.py          # coût JP tout compris vs prix FR (§3.6)
│  ├─ grading_roi.py        # plus-value de grading (§3.7)
│  ├─ signals.py            # détection pic prix/volume (§3.9)
│  └─ undervalue.py
├─ cogs/                    # commandes Discord par domaine
│  ├─ tracking.py
│  ├─ sold.py
│  ├─ monitor.py
│  ├─ calc.py
│  ├─ arbitrage.py
│  ├─ grading.py
│  ├─ sealed.py
│  ├─ knowledge.py
│  └─ daily.py
├─ ui/                      # discord.ui Views & Buttons (actions rapides §3.10)
├─ knowledge/               # .md remplis par toi
├─ Dockerfile
└─ docker-compose.yml
```

Livrables : code complet et commenté, `knowledge/` rempli, `README.md` (install, `.env`, lancement Docker, ajout/modif d'un scraper), et un `.env.example`.

---

## 7. Déroulé de développement

1. Squelette projet + bootstrap discord.py + base SQLite + Docker qui démarre.
2. Module `scrapers/base.py` (rate-limit/retry/playwright) + un premier scraper testé bout en bout (eBay via API Browse, le plus simple).
3. `/track` complet (3 plateformes) + déduplication + notifications.
4. `/sold`.
5. `fx_wise` + salon quotidien.
6. `/monitor` Cardmarket + historique + graphique.
7. Remplissage de `knowledge/` + commandes de consultation.
8. `services/pricing.py` + `/calc` (one-shot + assignation de salon) + `/convert` + sous-évaluation.
9. Fonctionnalités avancées (elles réutilisent `pricing.py`, `/sold` et `price_history` déjà en place) : radar d'arbitrage (§3.6), ROI de grading (§3.7), suivi de scellé (§3.8), détecteur de pic (§3.9).
10. **Actions rapides** (§3.10) : boutons sur les embeds d'alerte — le bouton lien dès l'étape 3, les boutons « calcule ma marge » et compagnie une fois `pricing.py` en place. Puis les extensions §5 rapides.

Commence par me proposer l'arborescence finale et le `docker-compose.yml`, puis avance étape par étape en me montrant le code de chaque module avant de passer au suivant. Pose-moi des questions si un choix d'implémentation est ambigu.
