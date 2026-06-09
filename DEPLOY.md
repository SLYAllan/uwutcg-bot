# Déploiement — VPS Hetzner (Docker, 24/7)

Le bot est un **worker** (pas de port web, pas de domaine/Traefik nécessaire). Il tourne en
conteneur, redémarre tout seul, et persiste sa base SQLite dans un volume.

> ⚠️ **Un seul bot à la fois avec le même token.** Avant de lancer sur le VPS, **arrête
> l'instance locale** (sinon Discord refuse la double connexion).

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

## 5. Option Coolify (comme riftboundfrance.fr)
- Nouveau service → **Docker Compose** (source = ton repo Git privé).
- Renseigner les variables d'env (le contenu du `.env`) dans l'onglet *Environment*.
- Monter des volumes persistants pour `/app/data` (et `/app/knowledge`, `/app/pricing.yaml`).
- Déploiement **manuel** (clic Deploy) — pas d'auto-deploy tant que la GitHub App n'est pas configurée.

## Exploitation
- Logs : `docker compose logs -f bot` (rotation 10 Mo × 3 déjà configurée).
- Redémarrer : `docker compose restart bot`
- Arrêter : `docker compose down`
- La base SQLite vit dans `./data/bot.db` (volume) → survit aux redéploiements.
- `knowledge/` et `pricing.yaml` sont montés en lecture seule → éditables sans rebuild (puis `restart`).

## Sécurité
- Régénère les secrets qui ont transité en clair (Bot Token Discord, keyset eBay) une fois en prod.
- Ne committe jamais `.env` (déjà dans `.gitignore` et `.dockerignore`).
