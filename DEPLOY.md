# Déploiement — VPS Hetzner (Docker, 24/7)

Le bot est un **worker** (pas de port web, pas de domaine/Traefik nécessaire). Il tourne en
conteneur, redémarre tout seul, et persiste sa base SQLite dans un volume.

> ⚠️ **Un seul bot à la fois avec le même token.** Avant de lancer sur le VPS, **arrête
> l'instance locale** (sinon Discord refuse la double connexion).

## Dépendances : lockfile (build reproductible)
Le Docker installe depuis **`requirements.lock`** (closure pinnée), pas `requirements.txt`.
Chaque rebuild Coolify est ainsi identique au bit près — une dep ne peut plus sauter de
version en silence (ce qui avait cassé monitor + FromJapan, cf. playwright-stealth 2.x).

Après toute modif de `requirements.txt`, **régénérer le lock** puis re-tester :
```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pip freeze > requirements.lock
.venv/Scripts/python -m pytest -q     # doit rester vert avant commit
```

## 0. Pré-requis sur le VPS
Docker + plugin compose installés :
```bash
docker --version && docker compose version
```

## 1. Récupérer le code sur le VPS

### Option A — via Git (recommandé)
Sur ta machine, pousser vers un dépôt **privé** :
```bash
# (une fois) créer le repo privé puis :
git remote add origin git@github.com:SLYAllan/uwutcg-bot.git
git push -u origin master
```
Sur le VPS :
```bash
git clone git@github.com:SLYAllan/uwutcg-bot.git
cd uwutcg-bot
```

### Option B — copie directe (sans GitHub)
Depuis ta machine (PowerShell), copier le projet **sans** le venv ni les données :
```powershell
# nécessite OpenSSH (présent sur Win11). Remplace USER/IP.
scp -r .\bot .\knowledge Dockerfile docker-compose.yml requirements.txt pricing.yaml pyproject.toml `
    USER@178.104.237.33:/opt/uwutcg-bot/
```

## 2. Créer le `.env` sur le VPS
Le `.env` n'est **pas** dans le dépôt (secrets). Le recréer sur le VPS :
```bash
cp .env.example .env
nano .env     # coller le BOT TOKEN, les clés eBay, etc.
```
(ou copier ton `.env` local via `scp .\.env USER@IP:/opt/uwutcg-bot/.env`)

## 3. Lancer
```bash
docker compose up -d --build
docker compose logs -f bot
```
Tu dois voir « Connecté en tant que MonitoringBot… » et « Slash commands synchronisées ».

## 4. Mises à jour ultérieures
```bash
git pull            # (option A) ou re-scp (option B)
docker compose up -d --build
```

## 5. Déploiement Coolify (recommandé — comme riftboundfrance.fr)

Coolify déploie depuis un **dépôt Git**. Étapes :

1. **Pousser le code sur un repo privé GitHub** (Coolify lira le `docker-compose.yml`) :
   ```bash
   git remote add origin git@github.com:SLYAllan/uwutcg-bot.git
   git push -u origin master
   ```
2. Dans Coolify : **+ New Resource → Private Repository (with GitHub App)** → sélectionner
   `SLYAllan/uwutcg-bot`, branche `master`.
3. **Build Pack : Docker Compose**, fichier `docker-compose.yml`.
4. **Environment Variables** : recopier le contenu de `.env` (DISCORD_TOKEN, DISCORD_APP_ID,
   EBAY_APP_ID, EBAY_DEV_ID, EBAY_CERT_ID, EBAY_MARKETPLACE_ID, TIMEZONE, etc.).
   Coolify les fournit au compose (le `env_file` est `required: false`, donc aucun fichier
   à créer ; pydantic-settings lit les variables d'environnement injectées).
5. **Persistance** : le volume nommé `bot-data` (→ `/app/data`, la base SQLite) est conservé
   automatiquement entre les redéploiements. `knowledge/` et `pricing.yaml` viennent du repo.
6. **Deploy** (manuel). Pas de domaine ni de port à exposer : c'est un worker.
7. Suivre les logs dans Coolify → tu dois voir « Connecté… » + « Slash commands synchronisées ».

> Mise à jour : `git push` puis re-cliquer **Deploy** dans Coolify (pas d'auto-deploy tant
> que le webhook/GitHub App n'est pas branché).

## Exploitation
- Logs : `docker compose logs -f bot` (rotation 10 Mo × 3 déjà configurée).
- Redémarrer : `docker compose restart bot`
- Arrêter : `docker compose down`
- La base SQLite vit dans `./data/bot.db` (volume) → survit aux redéploiements.
- `knowledge/` et `pricing.yaml` sont montés en lecture seule → éditables sans rebuild (puis `restart`).

## Sécurité
- Régénère les secrets qui ont transité en clair (Bot Token Discord, keyset eBay) une fois en prod.
- Ne committe jamais `.env` (déjà dans `.gitignore` et `.dockerignore`).
