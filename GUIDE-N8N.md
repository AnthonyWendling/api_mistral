# Utiliser l’API avec n8n

Ce guide explique comment appeler l’API Mistral (déployée sur Railway ou en local) depuis **n8n** : analyse de documents, indexation dans une base vectorielle, recherche, et flux RAG avec SharePoint / OneDrive.

---

## Prérequis

- n8n installé (self-hosted ou n8n.cloud).
- URL de l’API : `https://votre-api.up.railway.app` ou `http://localhost:8000`.
- Pour SharePoint / OneDrive : une connexion Microsoft configurée dans n8n.

---

## 1. Principe général

L’API ne se connecte **pas** à SharePoint. C’est **n8n** qui :

1. Se connecte à SharePoint (ou OneDrive) et récupère soit le **fichier** (binaire), soit une **URL de téléchargement**.
2. Envoie à l’API soit le fichier en **multipart**, soit l’URL dans un champ **`file_url`** (formulaire).

Tous les appels à l’API se font avec le nœud **HTTP Request**.

---

## 2. Configurer l’URL de base

Pour ne pas répéter l’URL partout :

1. Créez une **variable** n8n (Settings > Variables) ou utilisez une **constante** au début du workflow.
2. Exemple de valeur : `https://votre-api.up.railway.app`
3. Dans les nœuds HTTP Request, utilisez par exemple :  
   **URL** = `{{ $env.API_MISTRAL_URL || 'https://votre-api.up.railway.app' }}/analyze/document`  
   ou simplement l’URL complète si vous préférez.

Dans les exemples suivants, on notera **`BASE_URL`** : à remplacer par votre URL réelle.

---

## 3. Analyser un document (POST /analyze/document)

L’API extrait le texte du document, l’envoie à Mistral pour analyse et renvoie la réponse. Optionnellement, elle peut indexer le texte dans une collection.

### 3.1 Avec un fichier uploadé (binaire)

Utilisez quand un nœud en amont fournit un **fichier binaire** (ex. Microsoft OneDrive « Download », Trigger « Upload », etc.).

**Nœud : HTTP Request**

- **Method** : `POST`
- **URL** : `BASE_URL/analyze/document`
- **Send Body** : Oui
- **Body Content Type** : `Multipart-Form`
- **Specify Body** : Using Fields Below (ou équivalent)

**Champs du formulaire (Parameters / Form Data) :**

| Name | Type | Value |
|------|------|--------|
| file | Binary Data | Sélectionner le champ binaire du nœud précédent (ex. `$binary.data` ou le nom de la propriété binaire). |
| add_to_collection_id | String | Optionnel. Ex. : `ma-base` pour indexer dans la collection `ma-base`. |
| document_id | String | Optionnel. Ex. : `{{ $json.id }}` pour déduplication. |

Dans n8n, pour le champ **file** en type « Binary », choisir **Binary Property** = en général `data` (ou le nom de la propriété qui contient le fichier dans l’item entrant).

### 3.2 Avec une URL (file_url)

Utilisez quand vous avez une **URL de téléchargement** (ex. lien SharePoint/OneDrive fourni par un nœud Microsoft).

**Nœud : HTTP Request**

- **Method** : `POST`
- **URL** : `BASE_URL/analyze/document`
- **Send Body** : Oui
- **Body Content Type** : `Multipart-Form`

**Champs :**

| Name | Type | Value |
|------|------|--------|
| file_url | String | `{{ $json.downloadUrl }}` ou la propriété qui contient l’URL (selon le nœud Microsoft). |
| add_to_collection_id | String | Optionnel. Ex. : `ma-base` |
| document_id | String | Optionnel. Ex. : `{{ $json.id }}` |

### 3.3 Réponse

La sortie du nœud HTTP Request contient par exemple :

```json
{
  "analysis": "Résumé ou analyse du document par Mistral…",
  "add_to_collection_id": "ma-base",
  "indexed_chunks": 12
}
```

Vous pouvez utiliser `analysis` dans les nœuds suivants (affichage, envoi par email, etc.).

---

## 4. Créer une collection (POST /vectors/collections)

À faire une fois (ou dans un workflow d’initialisation).

**Nœud : HTTP Request**

- **Method** : `POST`
- **URL** : `BASE_URL/vectors/collections`
- **Send Body** : Oui
- **Body Content Type** : JSON
- **Body** :
  ```json
  {
    "name": "ma-base"
  }
  ```

Réponse : `{"id": "ma-base", "name": "ma-base"}`. L’**id** est celui à utiliser pour index et search.

---

## 5. Lister les collections (GET /vectors/collections)

**Nœud : HTTP Request**

- **Method** : `GET`
- **URL** : `BASE_URL/vectors/collections`

Réponse : `{"collections": [{"id": "ma-base", "name": "ma-base"}, ...]}`.

---

## 6. Indexer un document sans analyse (POST /vectors/collections/{id}/index)

Pour alimenter une base vectorielle **sans** poser de question à Mistral (extraction + découpage + embeddings + stockage uniquement).

Remplacez **`ma-base`** par l’**id** de votre collection.

### 6.1 Avec un fichier (binaire)

**Nœud : HTTP Request**

- **Method** : `POST`
- **URL** : `BASE_URL/vectors/collections/ma-base/index`
- **Send Body** : Oui
- **Body Content Type** : `Multipart-Form`

**Champs :**

| Name | Type | Value |
|------|------|--------|
| file | Binary Data | Propriété binaire de l’item (ex. `data`). |
| document_id | String | Optionnel. Ex. : `{{ $json.id }}` |

### 6.2 Avec une URL (file_url)

**Champs :**

| Name | Type | Value |
|------|------|--------|
| file_url | String | `{{ $json.downloadUrl }}` (ou la clé contenant l’URL). |
| document_id | String | Optionnel. |

### 6.3 Réponse

```json
{
  "collection_id": "ma-base",
  "indexed_chunks": 8
}
```

---

## 7. Recherche vectorielle (POST /vectors/collections/{id}/search)

Pour interroger la base par une question en langage naturel et récupérer les passages les plus pertinents.

**Nœud : HTTP Request**

- **Method** : `POST`
- **URL** : `BASE_URL/vectors/collections/ma-base/search`
- **Send Body** : Oui
- **Body Content Type** : JSON
- **Body** :
  ```json
  {
    "query": "{{ $json.question }}",
    "top_k": 5
  }
  ```

Adaptez **query** (ex. `$json.question`, `$json.query` ou une valeur fixe) et **top_k** (1–100).

Réponse : `{"results": [{ "chunk_id": "...", "text": "...", "metadata": {...}, "distance": 0.42 }, ...]}`.

Vous pouvez ensuite utiliser **results** dans un nœud Mistral / OpenAI pour un flux RAG (voir section 9).

---

## 8. Intégration SharePoint / OneDrive

### 8.1 Récupérer des fichiers depuis SharePoint

1. **Microsoft OneDrive** ou **Microsoft SharePoint** (selon votre version n8n) : nœud **« List »** ou **「Get All »** pour lister les fichiers d’un dossier.
2. Pour chaque fichier, utilisez une action du type **「Download »** ou **「Get file content »** pour obtenir :
   - soit le **binaire** du fichier (à envoyer en champ **file** à l’API),
   - soit une **URL de téléchargement** (à envoyer en **file_url**).

Selon le nœud Microsoft, le champ peut s’appeler `downloadUrl`, `webUrl`, ou être dans un sous-objet ; vérifiez la sortie du nœud dans n8n.

### 8.2 Workflow type : « Pour chaque fichier SharePoint → indexer dans l’API »

1. **Schedule** ou **Trigger** (optionnel).
2. **Microsoft OneDrive / SharePoint** : lister ou récupérer les fichiers (ex. d’un dossier « Documents à indexer »).
3. **HTTP Request** :  
   - POST `BASE_URL/vectors/collections/ma-base/index`  
   - Multipart : **file_url** = `{{ $json.downloadUrl }}` (ou **file** = binary si vous avez le binaire), **document_id** = `{{ $json.id }}`.
4. Optionnel : **IF** pour ne traiter que certains types (ex. `.pdf`).

### 8.3 Workflow type : « Analyser un document SharePoint et indexer »

1. Déclencheur ou nœud qui fournit le fichier ou l’URL (ex. OneDrive « Download »).
2. **HTTP Request** :  
   - POST `BASE_URL/analyze/document`  
   - **file_url** (ou **file**) + **add_to_collection_id** = `ma-base` + **document_id** si disponible.
3. Utiliser la réponse **analysis** (notification, enregistrement, etc.).

---

## 9. Flux RAG (recherche + réponse avec Mistral)

Objectif : l’utilisateur pose une question ; n8n interroge la base vectorielle, récupère les passages pertinents, puis envoie question + contexte à Mistral pour une réponse finale.

### 9.1 Schéma du flux

1. **Trigger** (Webhook, formulaire, etc.) : récupère la **question** de l’utilisateur.
2. **HTTP Request** : POST `BASE_URL/vectors/collections/ma-base/search` avec body `{"query": "{{ $json.question }}", "top_k": 5}`.
3. **Code** (ou **Set**) : construire un **contexte** à partir de `$json.results` (concaténer les `text` des chunks).
4. **Mistral** (ou **OpenAI**) : prompt du type « En te basant sur le contexte suivant, réponds à la question. Contexte : {{ contexte }}. Question : {{ question }} ».

### 9.2 Exemple de nœud Code (construire le contexte)

En entrée, l’item contient la réponse de l’API (objet avec `results`).

```javascript
const results = $input.item.json.results || [];
const context = results.map(r => r.text).join('\n\n');
return { json: { context, question: $input.item.json.question || $('Trigger').first().json.question } };
```

Adaptez les noms de propriétés selon votre trigger et le nœud HTTP Request (par ex. si la question est dans un autre nœud, utilisez `$('NomDuNoeud').first().json.question`).

### 9.3 Nœud Mistral

- **Resource** : Chat / Message.
- **Model** : au choix (ex. open-mistral-7b ou autre).
- **Messages** :  
  - System : « Tu réponds à la question en t’appuyant uniquement sur le contexte fourni. »  
  - User : « Contexte : {{ $json.context }}\n\nQuestion : {{ $json.question }} »

La sortie de ce nœud est la réponse RAG à renvoyer à l’utilisateur (Webhook response, email, etc.).

---

## 10. Résumé des URLs et des body

| Action | Method | URL | Body |
|--------|--------|-----|------|
| Analyser un document | POST | `BASE_URL/analyze/document` | Multipart : `file` ou `file_url` ; optionnel : `add_to_collection_id`, `document_id` |
| Créer une collection | POST | `BASE_URL/vectors/collections` | JSON : `{"name": "ma-base"}` |
| Lister les collections | GET | `BASE_URL/vectors/collections` | — |
| Indexer un document | POST | `BASE_URL/vectors/collections/{id}/index` | Multipart : `file` ou `file_url` ; optionnel : `document_id` |
| Recherche vectorielle | POST | `BASE_URL/vectors/collections/{id}/search` | JSON : `{"query": "...", "top_k": 10}` |

Remplacez **BASE_URL** par l’URL de votre API (Railway ou local) et **{id}** par l’identifiant de la collection (ex. `ma-base`).

---

## 11. Dépannage n8n

- **Erreur 400 « Fournir soit un fichier, soit file_url »** : vérifiez que vous envoyez bien un champ **file** (Binary Data) ou **file_url** (String), et que le nom du champ est exactement `file` ou `file_url`.
- **Erreur 404 sur /index ou /search** : l’**id** de la collection est incorrect ou la collection n’existe pas. Vérifiez avec GET `/vectors/collections`.
- **Binary non reconnu** : dans le nœud HTTP Request, pour le champ **file**, assurez-vous de choisir **Binary Data** et la bonne **Binary Property** (souvent `data`).
- **CORS** : si vous appelez l’API depuis l’interface n8n (front) et que le navigateur bloque, configurez `ALLOWED_ORIGINS` sur l’API (ou `*` en dev). En général, les workflows n8n s’exécutent côté serveur, donc CORS ne s’applique que si vous faites des appels depuis le front n8n.

Pour le déploiement de l’API sur Railway, reportez-vous au fichier **DEPLOIEMENT-RAILWAY.md**.
