# Documentation complète – API Mistral + recherche vectorielle

Cette API permet d’**analyser des documents** (PDF, Word, Excel, PPTX, images) via Mistral et de les **indexer dans des bases vectorielles** (Chroma + Mistral Embed) pour faire de la **recherche par similarité** (RAG, FAQ, etc.). Elle est conçue pour être utilisée depuis **n8n**, **Postman**, **cURL** ou tout client HTTP.

---

## Sommaire

1. [Vue d’ensemble](#1-vue-densemble)
2. [Installation et démarrage](#2-installation-et-démarrage)
3. [Configuration](#3-configuration)
4. [URL de base et conventions](#4-url-de-base-et-conventions)
5. [Endpoints](#5-endpoints)
6. [Formats de fichiers supportés](#6-formats-de-fichiers-supportés)
7. [Exemples cURL](#7-exemples-curl)
8. [Utilisation avec n8n](#8-utilisation-avec-n8n)
9. [Codes d’erreur et limites](#9-codes-derreur-et-limites)
10. [Bonnes pratiques](#10-bonnes-pratiques)

---

## 1. Vue d’ensemble

| Fonctionnalité | Description |
|----------------|-------------|
| **Analyse de document** | Envoi d’un fichier ou d’une URL → extraction du texte → analyse par Mistral → réponse structurée. Option : indexation automatique dans une collection. |
| **Collections vectorielles** | Création et liste de bases vectorielles (une collection = une base Chroma). |
| **Indexation** | Ajout de documents dans une collection (extraction → découpage en chunks → embeddings Mistral → stockage) sans poser de question à l’agent. |
| **Recherche** | Requête en langage naturel → embedding → recherche par similarité → retour des passages les plus pertinents (pour RAG, FAQ, etc.). |

**Flux typique :**

1. Créer une collection : `POST /vectors/collections` avec `{"name": "ma-base"}`.
2. Alimenter la base : analyser des documents avec `add_to_collection_id` ou indexer directement avec `POST /vectors/collections/{id}/index`.
3. Interroger : `POST /vectors/collections/{id}/search` avec `{"query": "..."}` puis utiliser les chunks dans n8n ou un autre agent.

---

## 2. Installation et démarrage

### Prérequis

- Python 3.11+
- Clé API Mistral ([https://console.mistral.ai](https://console.mistral.ai))
- Pour l’OCR des images : Tesseract installé et dans le PATH (optionnel en local)

### Installation

```bash
# Cloner ou aller dans le projet
cd api_mistral

# Créer l’environnement virtuel
python -m venv .venv

# Activer (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activer (Linux / macOS)
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt
```

### Démarrage

```bash
uvicorn app.main:app --reload --port 8000
```

- **API** : [http://localhost:8000](http://localhost:8000)  
- **Documentation interactive (Swagger)** : [http://localhost:8000/docs](http://localhost:8000/docs)  
- **Healthcheck** : [http://localhost:8000/health](http://localhost:8000/health)

---

## 3. Configuration

Toutes les options sont pilotées par des **variables d’environnement** (ou un fichier `.env` à la racine du projet).

| Variable | Obligatoire | Description | Valeur par défaut |
|----------|-------------|-------------|-------------------|
| `MISTRAL_API_KEY` | Oui | Clé API Mistral | — |
| `CHROMA_DATA_PATH` | Non | Dossier de persistance Chroma (sur Railway : volume, ex. `/data/chroma`) | `./data/chroma` |
| `LOG_LEVEL` | Non | Niveau de log (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `MAX_FILE_SIZE_MB` | Non | Taille max d’un fichier en Mo | `50` |
| `ALLOWED_ORIGINS` | Non | Origines CORS (séparées par des virgules, ou `*`) | `*` |
| `CHUNK_SIZE` | Non | Nombre de caractères par chunk pour l’indexation | `512` |
| `CHUNK_OVERLAP` | Non | Chevauchement entre deux chunks (caractères) | `128` |

Exemple de `.env` :

```env
MISTRAL_API_KEY= votre_cle_mistral
CHROMA_DATA_PATH=./data/chroma
MAX_FILE_SIZE_MB=50
ALLOWED_ORIGINS=*
```

---

## 4. URL de base et conventions

- **En local** : `http://localhost:8000`
- **Sur Railway** : `https://votre-projet.up.railway.app`

Tous les endpoints sont décrits sous cette **base URL**. L’API ne nécessite pas d’authentification côté serveur (vous pouvez ajouter une clé API ou un JWT devant l’API avec un reverse proxy si besoin).

**Content-Type :**

- **JSON** : pour les body en JSON (`Content-Type: application/json`).
- **Multipart** : pour l’envoi de fichier + champs formulaire (`Content-Type: multipart/form-data`).

---

## 5. Endpoints

### 5.1 Santé de l’API

**GET /health**

Vérifie que l’API répond (utilisé par Railway pour le healthcheck).

**Réponse (200)**  
```json
{"status": "ok"}
```

---

### 5.2 Analyse de document

**POST /analyze/document**

Envoie un document (fichier ou URL), extrait le texte, l’envoie à Mistral pour analyse et renvoie la réponse. Optionnellement, indexe le texte dans une collection vectorielle.

**Corps de la requête :** `multipart/form-data`

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `file` | Fichier | Oui* | Fichier à analyser (PDF, Word, Excel, PPTX, image). |
| `file_url` | Chaîne | Oui* | URL publique du document (ex. lien de téléchargement SharePoint fourni par n8n). |
| `add_to_collection_id` | Chaîne | Non | Identifiant de la collection dans laquelle indexer le texte (ex. `ma-base`). |
| `document_id` | Chaîne | Non | Identifiant unique du document pour la déduplication (évite de ré-indexer le même document). |

\* Il faut **soit** `file`, **soit** `file_url`, pas les deux obligatoirement. Si les deux sont fournis, le fichier uploadé est utilisé.

**Réponse (200)**  
```json
{
  "analysis": "Texte d’analyse généré par Mistral…",
  "add_to_collection_id": "ma-base",
  "indexed_chunks": 12
}
```

- `analysis` : réponse de l’agent Mistral.
- `indexed_chunks` : nombre de chunks ajoutés à la collection (0 si pas d’indexation ou déduplication).

**Erreurs possibles**

- **400** : Aucun fichier ni `file_url`, type de document non supporté, ou fichier trop volumineux.

---

### 5.3 Créer une collection

**POST /vectors/collections**

Crée une nouvelle base vectorielle (collection Chroma).

**Corps (JSON)**  
```json
{
  "name": "ma-collection"
}
```

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `name` | Chaîne | Oui | Nom lisible. L’identifiant technique (slug) est dérivé automatiquement (ex. `ma-collection` → id `ma-collection`). |

**Réponse (200)**  
```json
{
  "id": "ma-collection",
  "name": "ma-collection"
}
```

`id` est celui à utiliser dans les endpoints `/vectors/collections/{id}/index` et `/vectors/collections/{id}/search`.

---

### 5.4 Lister les collections

**GET /vectors/collections**

Retourne la liste des collections existantes.

**Réponse (200)**  
```json
{
  "collections": [
    {"id": "ma-collection", "name": "ma-collection"},
    {"id": "autre-base", "name": "autre-base"}
  ]
}
```

---

### 5.5 Indexer un document (sans analyse)

**POST /vectors/collections/{collection_id}/index**

Indexe un document dans une collection : extraction du texte → découpage en chunks → embeddings Mistral → stockage. **Aucun appel à l’agent Mistral** (pas de question/réponse).

**Paramètre de chemin**

- `collection_id` : identifiant de la collection (ex. `ma-collection`).

**Corps :** `multipart/form-data`

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `file` | Fichier | Oui* | Fichier à indexer. |
| `file_url` | Chaîne | Oui* | URL du document à télécharger. |
| `document_id` | Chaîne | Non | Identifiant pour déduplication (évite de ré-indexer le même document). |

\* Il faut **soit** `file`, **soit** `file_url`.

**Réponse (200)**  
```json
{
  "collection_id": "ma-collection",
  "indexed_chunks": 8
}
```

Si aucun texte n’est extrait :  
```json
{
  "collection_id": "ma-collection",
  "indexed_chunks": 0,
  "message": "Aucun texte extrait."
}
```

**Erreurs**

- **400** : Aucun fichier ni `file_url`, type non supporté, ou fichier trop volumineux.
- **404** : Collection inexistante.

---

### 5.6 Recherche vectorielle

**POST /vectors/collections/{collection_id}/search**

Recherche par similarité sémantique dans une collection : la requête est transformée en vecteur (Mistral Embed) puis comparée aux chunks indexés.

**Paramètre de chemin**

- `collection_id` : identifiant de la collection.

**Corps (JSON)**  
```json
{
  "query": "Quelle est la politique de congés ?",
  "top_k": 10
}
```

| Champ | Type | Obligatoire | Description |
|-------|------|-------------|-------------|
| `query` | Chaîne | Oui | Question ou phrase de recherche. |
| `top_k` | Entier | Non | Nombre de résultats à retourner (1–100). Défaut : 10. |

**Réponse (200)**  
```json
{
  "results": [
    {
      "chunk_id": "abc123_0",
      "text": "Extrait du document…",
      "metadata": {
        "source_file": "document.pdf",
        "file_url": "https://…",
        "index": 0,
        "date": "2025-02-25T10:00:00+00:00",
        "document_id": "abc123"
      },
      "distance": 0.42
    }
  ]
}
```

- `distance` : plus elle est **faible**, plus le chunk est pertinent (similarité cosinus dans Chroma).
- Les champs `metadata` permettent de savoir d’où vient le passage (fichier, URL, date).

**Erreurs**

- **404** : Collection inexistante.

---

## 6. Formats de fichiers supportés

| Type | Extensions | Méthode |
|------|------------|---------|
| PDF | `.pdf` | Extraction de texte (pypdf) |
| Word | `.docx` | python-docx |
| Excel | `.xlsx` | openpyxl (texte des cellules) |
| PowerPoint | `.pptx` | python-pptx (texte des slides) |
| Images | `.png`, `.jpg`, `.jpeg`, `.gif` | OCR (Tesseract) |

La détection se fait par **extension** du fichier ou par **Content-Type** si l’URL ne contient pas d’extension. Tout autre type renvoie une erreur **400** avec un message explicite.

---

## 7. Exemples cURL

Remplacez `BASE_URL` par `http://localhost:8000` ou l’URL Railway.

**Healthcheck**
```bash
curl -X GET "%BASE_URL%/health"
```

**Créer une collection**
```bash
curl -X POST "%BASE_URL%/vectors/collections" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\": \"ma-base\"}"
```

**Lister les collections**
```bash
curl -X GET "%BASE_URL%/vectors/collections"
```

**Analyser un fichier local (et indexer dans une collection)**
```bash
curl -X POST "%BASE_URL%/analyze/document" ^
  -F "file=@C:\chemin\vers\document.pdf" ^
  -F "add_to_collection_id=ma-base" ^
  -F "document_id=doc-001"
```

**Analyser un document via URL**
```bash
curl -X POST "%BASE_URL%/analyze/document" ^
  -F "file_url=https://exemple.com/document.docx" ^
  -F "add_to_collection_id=ma-base"
```

**Indexer un fichier (sans analyse)**
```bash
curl -X POST "%BASE_URL%/vectors/collections/ma-base/index" ^
  -F "file=@C:\chemin\vers\rapport.xlsx" ^
  -F "document_id=rapport-2025"
```

**Indexer via URL**
```bash
curl -X POST "%BASE_URL%/vectors/collections/ma-base/index" ^
  -F "file_url=https://sharepoint.com/.../fichier.pdf"
```

**Recherche**
```bash
curl -X POST "%BASE_URL%/vectors/collections/ma-base/search" ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"politique de télétravail\", \"top_k\": 5}"
```

Sur Linux/macOS, remplacer `^` par `\` en fin de ligne.

---

## 8. Utilisation avec n8n

### Principe

- n8n se connecte à **SharePoint / OneDrive** (nœuds Microsoft).
- L’API ne se connecte **pas** à SharePoint : elle reçoit soit un **fichier** (binaire), soit une **URL** de téléchargement.

### Scénarios courants

**1. Analyser un fichier SharePoint**

- Nœud **Microsoft OneDrive** ou **SharePoint** : récupérer le fichier ou l’URL de téléchargement.
- Nœud **HTTP Request** :
  - Method : `POST`
  - URL : `https://votre-api.up.railway.app/analyze/document`
  - Body Content Type : `Multipart-Form`
  - Champs :
    - `file` (Binary Data) si vous avez le binaire du fichier, **ou**
    - `file_url` (String) avec l’URL de téléchargement
  - Optionnel : `add_to_collection_id`, `document_id`

**2. Indexer des documents sans analyse**

- Même idée : récupérer le fichier ou l’URL dans SharePoint.
- HTTP Request :
  - `POST https://votre-api.up.railway.app/vectors/collections/MA_COLLECTION_ID/index`
  - Multipart : `file` ou `file_url`, optionnel `document_id`

**3. RAG : recherche puis envoi à un agent**

- HTTP Request : `POST .../vectors/collections/MA_COLLECTION_ID/search` avec body JSON `{"query": "{{ $json.question }}", "top_k": 5}`.
- Utiliser la sortie `results` (chunks + métadonnées) pour construire un contexte et l’envoyer à un nœud **Mistral** / **OpenAI** ou à une autre requête vers votre API (ex. un endpoint qui prend les chunks + une question et appelle Mistral).

### Exemple de champs n8n (HTTP Request – multipart)

| Name | Type | Value |
|-----|------|--------|
| file | Binary Data | (mapping depuis le nœud SharePoint) |
| add_to_collection_id | String | ma-base |
| document_id | String | {{ $json.id }} |

Si vous utilisez une URL au lieu du binaire :

| Name | Type | Value |
|-----|------|--------|
| file_url | String | {{ $json.downloadUrl }} |

---

## 9. Codes d’erreur et limites

| Code HTTP | Signification |
|-----------|----------------|
| 400 | Requête invalide : fichier/URL manquant, type non supporté, fichier trop gros, ou paramètre incorrect. |
| 404 | Ressource introuvable (ex. collection_id inexistant pour index ou search). |
| 500 | Erreur serveur (ex. erreur Mistral, Chroma, ou extraction). |

**Limites techniques**

- Taille max d’un fichier : définie par `MAX_FILE_SIZE_MB` (défaut 50 Mo).
- Le texte envoyé à Mistral pour l’analyse est tronqué au-delà d’environ 128 000 caractères.
- Recherche : `top_k` entre 1 et 100.

En cas d’erreur, le body de la réponse contient souvent un message explicite (ex. `{"detail": "Type de document non supporté: .xyz"}`).

---

## 10. Bonnes pratiques

- **Déduplication** : utiliser un `document_id` stable (ex. ID SharePoint, hash du nom + date) pour éviter de ré-indexer le même document.
- **Nommage des collections** : utiliser des noms courts et en minuscules (le slug dérive du nom).
- **RAG** : indexer d’abord les documents avec `/index` ou `add_to_collection_id`, puis interroger avec `/search` et envoyer les chunks les plus pertinents à un agent (Mistral, OpenAI, etc.) avec la question de l’utilisateur.
- **Railway** : monter un volume sur un chemin fixe (ex. `/data`) et définir `CHROMA_DATA_PATH=/data/chroma` pour que les collections survivent aux redéploiements.
- **CORS** : en production, restreindre `ALLOWED_ORIGINS` aux domaines de vos front ou à l’URL de n8n si nécessaire.

---

Pour une prise en main rapide, ouvrez **Swagger** : [http://localhost:8000/docs](http://localhost:8000/docs) (ou votre URL Railway + `/docs`).
