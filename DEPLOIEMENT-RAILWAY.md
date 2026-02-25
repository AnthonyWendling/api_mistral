# Déploiement de l’API sur Railway

Ce guide décrit pas à pas comment déployer l’API Mistral + recherche vectorielle sur **Railway** et configurer le **volume** pour que les bases vectorielles (Chroma) soient conservées après chaque redéploiement.

---

## Prérequis

- Un compte [Railway](https://railway.app)
- Le code du projet poussé sur **GitHub** (ou GitLab / Bitbucket connecté à Railway)
- Une **clé API Mistral** ([console Mistral](https://console.mistral.ai))

---

## 1. Créer un projet Railway

1. Allez sur [railway.app](https://railway.app) et connectez-vous.
2. Cliquez sur **« New Project »**.
3. Choisissez **« Deploy from GitHub repo »** (ou votre hébergeur Git).
4. Autorisez Railway à accéder à votre dépôt si besoin.
5. Sélectionnez le dépôt **api_mistral** (ou le nom de votre repo).
6. Railway crée un projet et détecte le **Dockerfile** pour le build.

---

## 2. Configurer le service

### 2.1 Build

- Railway utilise le **Dockerfile** à la racine du projet (défini dans `railway.json`).
- Aucune action supplémentaire : le build se lance automatiquement à chaque push.

### 2.2 Port

- Railway fournit la variable d’environnement **`PORT`**.
- Le `railway.json` contient déjà :  
  `"startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT"`  
  Le service écoute donc sur le port indiqué par Railway.

### 2.3 Variables d’environnement

Dans le projet Railway, ouvrez votre **service** (le déploiement), puis **Variables** (ou **Settings > Variables**).

Ajoutez au minimum :

| Variable | Valeur | Obligatoire |
|----------|--------|-------------|
| `MISTRAL_API_KEY` | Votre clé API Mistral | Oui |
| `CHROMA_DATA_PATH` | `/data/chroma` | Oui si vous utilisez un volume (recommandé) |

Optionnel :

| Variable | Valeur | Description |
|----------|--------|-------------|
| `LOG_LEVEL` | `INFO` | Niveau de log |
| `MAX_FILE_SIZE_MB` | `50` | Taille max des fichiers (Mo) |
| `ALLOWED_ORIGINS` | `*` ou `https://votre-n8n.com` | CORS |

**Important :** Ne définissez `CHROMA_DATA_PATH` qu’**après** avoir créé et monté le volume (étape 3). Sans volume, vous pouvez laisser la valeur par défaut (`./data/chroma`) : les données seront perdues à chaque redéploiement.

---

## 3. Créer et monter un volume (persistance Chroma)

Sans volume, le système de fichiers du conteneur est éphémère : les **collections vectorielles** sont perdues à chaque nouveau déploiement.

### 3.1 Créer le volume

1. Dans votre projet Railway, ouvrez le **service** (votre API).
2. Allez dans l’onglet **« Volumes »** (ou **Settings > Volumes**).
3. Cliquez sur **« Add Volume »** (ou **« New Volume »**).
4. Donnez un nom (ex. `chroma-data`).
5. Choisissez un **chemin de montage** : **`/data`** (recommandé).

Le volume sera monté dans le conteneur au chemin `/data`.

### 3.2 Variable CHROMA_DATA_PATH

Une fois le volume créé et monté sur `/data` :

1. Allez dans **Variables** du service.
2. Ajoutez ou modifiez :  
   **`CHROMA_DATA_PATH`** = **`/data/chroma`**

L’API créera le dossier `chroma` dans le volume. Toutes les collections Chroma seront stockées là et **persisteront** après un redéploiement ou un redémarrage.

### 3.3 Résumé

- **Volume** : monté en `/data`
- **Variable** : `CHROMA_DATA_PATH=/data/chroma`
- Les données Chroma sont sur le volume, pas sur le disque éphémère du conteneur.

---

## 4. Domaine public (URL de l’API)

1. Dans le service, allez dans **Settings** (ou l’onglet **Networking**).
2. Section **「Public Networking」** ou **「Generate Domain」**.
3. Cliquez sur **「Generate Domain」** (ou **「Add domain」**).
4. Railway vous donne une URL du type :  
   **`https://votre-service-xxx.up.railway.app`**

Cette URL est celle à utiliser dans **n8n** et dans tous vos appels (Postman, cURL, etc.).

Exemples d’endpoints :

- Healthcheck : `https://votre-service-xxx.up.railway.app/health`
- Documentation : `https://votre-service-xxx.up.railway.app/docs`
- Analyse : `https://votre-service-xxx.up.railway.app/analyze/document`

---

## 5. Healthcheck

Le fichier `railway.json` contient :

```json
"healthcheckPath": "/health",
"healthcheckTimeout": 30
```

Railway appelle **GET /health** pour vérifier que l’API répond. Si l’endpoint renvoie **200** avec `{"status": "ok"}`, le déploiement est considéré en bonne santé.

Aucune configuration supplémentaire à faire si vous n’avez pas modifié la route `/health`.

---

## 6. Redéploiement

- **Automatique** : à chaque **push** sur la branche connectée (souvent `main`), Railway rebuild et redéploie.
- **Manuel** : dans le dashboard Railway, onglet **Deployments**, bouton **「Redeploy」** sur le dernier déploiement.

Après un redéploiement, les **variables d’environnement** et le **volume** restent inchangés ; seuls le code et l’image Docker sont mis à jour. Les collections Chroma sur le volume sont conservées.

---

## 7. Vérifications après déploiement

1. **Healthcheck**  
   Ouvrez dans un navigateur :  
   `https://votre-domaine.up.railway.app/health`  
   Réponse attendue : `{"status":"ok"}`.

2. **Documentation**  
   Ouvrez :  
   `https://votre-domaine.up.railway.app/docs`  
   Vous devez voir Swagger avec tous les endpoints.

3. **Création d’une collection** (test rapide)  
   ```bash
   curl -X POST "https://votre-domaine.up.railway.app/vectors/collections" \
     -H "Content-Type: application/json" \
     -d "{\"name\": \"test\"}"
   ```  
   Réponse attendue : `{"id":"test","name":"test"}`.

Si une de ces étapes échoue, consultez la section **Dépannage** ci-dessous.

---

## 8. Dépannage

### L’API ne démarre pas ou crash au démarrage

- Vérifiez les **logs** du service dans Railway (onglet **Deployments** > dernier déploiement > **View Logs**).
- Vérifiez que **`MISTRAL_API_KEY`** est bien définie et valide.
- Si vous utilisez un volume : vérifiez que **`CHROMA_DATA_PATH`** pointe vers un chemin **dans** le volume (ex. `/data/chroma`), pas vers un chemin en dehors.

### Les collections disparaissent après un redéploiement

- Vous n’utilisez probablement **pas** de volume, ou **`CHROMA_DATA_PATH`** ne pointe pas vers le volume.
- Créez un volume monté sur `/data`, définissez `CHROMA_DATA_PATH=/data/chroma`, puis redéployez. Les nouvelles collections seront persistées.

### Erreur 502 / timeout

- Le premier démarrage (installation des dépendances dans l’image) est déjà fait au build. Si le healthcheck échoue au démarrage, augmentez **healthcheckTimeout** dans `railway.json` (ex. 60).
- Vérifiez que la commande de démarrage utilise bien **`$PORT`** (déjà le cas dans `railway.json`).

### Build Docker échoue

- Vérifiez que **Dockerfile** et **requirements.txt** sont à la racine du repo et committés.
- En local : `docker build -t api_mistral .` pour reproduire le build.

---

## 9. Récapitulatif

| Étape | Action |
|-------|--------|
| 1 | Créer un projet Railway et connecter le repo GitHub (api_mistral). |
| 2 | Ajouter les variables : `MISTRAL_API_KEY`, puis après création du volume : `CHROMA_DATA_PATH=/data/chroma`. |
| 3 | Créer un volume, montage sur `/data`. |
| 4 | Générer un domaine public et noter l’URL (pour n8n et les tests). |
| 5 | Tester `/health`, `/docs` et un appel (ex. création de collection). |

Une fois ces points en place, l’API est prête à être utilisée depuis **n8n** ou tout autre client. Pour l’intégration n8n, voir le fichier **GUIDE-N8N.md**.
