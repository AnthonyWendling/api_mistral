# SharePoint : recherche de documents spécifiques et lien avec Mistral

Ce guide clarifie la différence entre **l’API Files de Mistral** et votre besoin **« aller chercher des documents spécifiques dans SharePoint via une recherche »**, puis décrit comment mettre en place le flux.

---

## 0. Comment fonctionne la recherche vectorielle (dans cette API)

La **recherche vectorielle** (sémantique) ne cherche pas par mots-clés : elle compare le **sens** de ta question à celui des textes indexés.

### En amont : indexation

1. **Document** (PDF, Word, etc.) → extraction du texte → découpage en **chunks** (morceaux de ~512 caractères avec chevauchement).
2. Chaque chunk est envoyé à **Mistral Embed** → on obtient un **vecteur** (liste de nombres) qui représente le sens du texte.
3. Ces vecteurs + le texte + les métadonnées (nom du fichier, `sharepoint_item_id`, etc.) sont stockés dans **Chroma** (base vectorielle), dans une **collection** (ex. `affaires-commerciales`).

Résultat : la collection contient des **chunks** avec leur **embedding** (vecteur) et leurs métadonnées.

### Au moment de la recherche

1. L’utilisateur envoie une **question** (ex. « Où est le template mail Power Automate ? »).
2. La même **Mistral Embed** transforme cette question en un **vecteur**.
3. **Chroma** compare ce vecteur à tous les vecteurs de la collection (similarité cosinus ou distance) et renvoie les **top_k** chunks les plus proches (les plus « similaires en sens »).
4. L’API renvoie ces chunks + les **métadonnées** (dont `sharepoint_item_id`, `source_file`, etc.) pour que n8n puisse télécharger le bon fichier depuis SharePoint.

### Où ça se passe dans le code

| Étape | Fichier / endpoint |
|-------|--------------------|
| Embedding des chunks (indexation) | `embedding_service.embed_texts()` → Mistral Embed |
| Stockage | `vector_store_service.add_documents()` → Chroma |
| Embedding de la requête | `embedding_service.embed_query()` |
| Recherche par similarité | `vector_store_service.search()` → Chroma `query()` |
| API recherche « brute » | `POST /vectors/collections/{id}/search` |
| API recherche + docs pour SharePoint | `POST /webhooks/search-documents` |
| RAG (recherche + réponse IA) | `POST /webhooks/rag` |

En résumé : **texte → vecteurs (Mistral Embed) → stockage (Chroma) → à la requête, la question est aussi vectorisée → Chroma renvoie les chunks les plus proches en sens.**

---

## 1. API Files Mistral vs votre besoin

### L’API Files de Mistral ([docs](https://docs.mistral.ai/api/endpoint/files))

- **Rôle** : gérer des **fichiers stockés chez Mistral** (upload, list, retrieve, delete, download).
- **Cas d’usage** : fine-tuning (fichiers .jsonl), jobs batch, OCR sur des fichiers hébergés par Mistral.
- **Limite** : elle **ne se connecte pas à SharePoint**. C’est un stockage côté Mistral, pas un connecteur SharePoint.

Donc : **on ne « branche » pas l’API Files Mistral sur SharePoint**. Pour « aller dans SharePoint chercher des documents spécifiques », on utilise **Microsoft Graph** (recherche SharePoint/OneDrive) puis, si besoin, on envoie les fichiers ou URLs vers **votre API** (analyse / indexation vectorielle).

### Votre besoin : SharePoint → recherche → documents spécifiques

Objectif : **depuis une recherche (mot-clé, question, etc.), trouver des documents dans SharePoint** puis les utiliser (indexation, analyse, RAG).

Deux approches possibles :

| Approche | Où se fait la recherche | Rôle de l’API Mistral (votre projet) |
|----------|-------------------------|--------------------------------------|
| **A. Recherche native SharePoint** | Microsoft Graph (recherche par nom/métadonnées/contenu) | Recevoir la liste des fichiers trouvés (ou leurs URLs), puis analyser/indexer |
| **B. Recherche sémantique (RAG)** | Votre API (recherche vectorielle dans les collections déjà indexées) | Recherche par sens → retourne les bons documents avec `sharepoint_item_id` → n8n télécharge depuis SharePoint |

Vous pouvez combiner les deux : **recherche SharePoint** pour cibler des dossiers/fichiers, puis **indexation / recherche sémantique** dans votre API.

---

## 2. Mise en place : recherche dans SharePoint puis envoi à votre API

Pour « aller dans SharePoint chercher des documents spécifiques (via une recherche) » et les envoyer à votre API (ou à Mistral), le flux est le suivant.

### 2.1 Recherche dans SharePoint (Microsoft Graph)

Deux options côté Microsoft Graph :

#### Option 1 : Recherche dans un lecteur (drive) donné

- **Endpoint** : `GET /drives/{drive-id}/root/search(q='{texte}')`  
  ou pour un site : `GET /sites/{site-id}/drive/root/search(q='{texte}')`
- **Droits** : `Files.Read` (ou équivalent).
- **Utilité** : rechercher par nom, métadonnées ou contenu **dans un drive/site précis**.

Exemple (à adapter dans n8n avec un nœud **HTTP Request** ou le connecteur Microsoft si disponible) :

```http
GET https://graph.microsoft.com/v1.0/sites/{site-id}/drive/root/search(q='template Power Automate')
```

Réponse : liste de `driveItem` avec `id`, `name`, `parentReference` (driveId, path), `webUrl`, etc.

#### Option 2 : Microsoft Search API (recherche globale)

- **Endpoint** : `POST https://graph.microsoft.com/v1.0/search/query`
- **Body** :

```json
{
  "requests": [{
    "entityTypes": ["driveItem"],
    "query": {
      "queryString": "template Power Automate"
    }
  }]
}
```

- **Droits** : `Files.Read.All` ou `Files.ReadWrite.All`.
- **Utilité** : recherche sur plusieurs drives / sites (OneDrive + SharePoint).

Références : [Search driveItem](https://learn.microsoft.com/en-us/graph/api/driveitem-search), [Microsoft Search API](https://learn.microsoft.com/en-us/graph/search-concept-files).

### 2.2 Flux global dans n8n

Schéma du flux **« recherche SharePoint → documents spécifiques → votre API »** :

```
[Déclencheur : Webhook / Schedule / Manuel]
         ↓
[HTTP Request : Microsoft Graph – recherche SharePoint]
  → GET .../drive/root/search(q='...')  OU  POST .../search/query
         ↓
[Sortie : liste de driveItem avec id, name, webUrl, parentReference]
         ↓
[Filtrer par type (fichiers uniquement) si besoin]
         ↓
[Pour chaque item (ou un sous-ensemble)]
   → [Microsoft OneDrive/SharePoint : Download avec item id]
   → [HTTP Request : POST votre-api/vectors/collections/{id}/index
        file = binaire, document_id = id SharePoint, sharepoint_item_id, drive_id, folder_path, site_id]
```

- **Recherche** : soit par **nom/métadonnées/contenu** (Graph), soit plus tard par **sens** (recherche vectorielle de votre API sur des collections déjà remplies).
- **Documents spécifiques** : ce sont les `driveItem` retournés par la recherche Graph ; vous choisissez lesquels envoyer à l’indexation (tous ou après filtre).

### 2.3 Exemple concret dans n8n

1. **Déclencheur** : Webhook (body avec `{"query": "contrat type X"}`) ou Manual Trigger.
2. **HTTP Request** (Microsoft Graph) :
   - **Méthode** : GET  
   - **URL** : `https://graph.microsoft.com/v1.0/sites/{{ $env.SITE_ID }}/drive/root/search(q='{{ $json.query }}')`  
   - **Auth** : OAuth2 (compte Microsoft avec droits sur le site).
3. **Code ou Set** : partir de `body.value` (liste des `driveItem`), garder seulement les fichiers (par exemple où `file` est présent), et éventuellement limiter à N premiers.
4. **Boucle** sur chaque item :
   - **Microsoft OneDrive / SharePoint** : **Download** avec **Item ID** = `{{ $json.id }}`, **Drive ID** = `{{ $json.parentReference.driveId }}`.
   - **HTTP Request** vers votre API :
     - **URL** : `https://apimistral-production.up.railway.app/vectors/collections/MA_COLLECTION/index`
     - **Body** : multipart/form-data  
       - `file` : binaire (propriété du nœud Download)  
       - `document_id` : `{{ $json.id }}`  
       - `sharepoint_item_id` : `{{ $json.id }}`  
       - `drive_id` : `{{ $json.parentReference.driveId }}`  
       - `folder_path` : `{{ $json.parentReference.path }}`  
       - `site_id` : `{{ $json.parentReference.siteId }}`

Ainsi, la **recherche** est faite dans SharePoint (Graph), et seuls les **documents spécifiques** retournés sont téléchargés puis indexés dans votre API (avec métadonnées SharePoint pour pouvoir les retrouver ensuite via `search-documents`).

---

## 3. Utiliser la recherche sémantique (déjà en place) pour « documents spécifiques »

Vous avez déjà un flux **recherche par sens → bon fichier SharePoint** :

1. **Indexation** : fichiers SharePoint envoyés à votre API avec `sharepoint_item_id`, `drive_id`, `folder_path`, `site_id` (voir **N8N-SYNC-SHAREPOINT-VERS-COLLECTION.md** et **N8N-SHAREPOINT-RECHERCHE.md**).
2. **Recherche** : `POST /webhooks/search-documents` avec `query` + `collection_id` → l’API retourne les documents les plus pertinents **avec** `sharepoint_item_id`, etc.
3. **Téléchargement** : n8n utilise **Microsoft OneDrive/SharePoint – Download** avec `sharepoint_item_id` (et `drive_id` si besoin) pour récupérer le bon fichier.

C’est déjà « aller dans SharePoint chercher des documents spécifiques **via une recherche** » : la recherche est sémantique (votre API), et le « lieu » où sont les fichiers reste SharePoint.

---

## 4. Si vous voulez aussi utiliser l’API Files de Mistral

Si vous avez un besoin précis d’**uploader des fichiers vers le stockage Mistral** (ex. pour un job batch ou de l’OCR côté Mistral) :

- Vous **récupérez** d’abord le fichier depuis SharePoint (n8n + Graph, comme ci-dessus).
- Puis vous appelez l’**API Files Mistral** :
  - **Upload** : `POST https://api.mistral.ai/v1/files` (multipart : `file` + `purpose` : `"batch"` | `"fine-tune"` | `"ocr"`).
  - **List** : `GET https://api.mistral.ai/v1/files` (liste des fichiers côté Mistral).
- Cela reste **découplé** de SharePoint : SharePoint sert de source ; Mistral Files sert de stockage côté Mistral pour leurs propres traitements.

---

## 5. Résumé

| Question | Réponse |
|----------|---------|
| **L’API Files Mistral peut-elle aller chercher des docs dans SharePoint ?** | Non. C’est un stockage Mistral, pas un connecteur SharePoint. |
| **Comment « aller dans SharePoint chercher des documents spécifiques via une recherche » ?** | **Recherche** : Microsoft Graph (`/drive/root/search(q='...')` ou `POST /search/query`). **Envoi à votre API** : n8n télécharge chaque fichier (OneDrive/SharePoint) puis appelle `POST /vectors/collections/{id}/index` (et optionnellement analyse). |
| **Recherche par sens (sémantique) ?** | Déjà en place : indexation avec métadonnées SharePoint → `POST /webhooks/search-documents` → téléchargement dans SharePoint avec `sharepoint_item_id` (voir **N8N-SHAREPOINT-RECHERCHE.md**). |

En pratique : **recherche SharePoint = Microsoft Graph** ; **recherche sémantique + stockage des références SharePoint = votre API + n8n** ; **stockage de fichiers côté Mistral = API Files Mistral**, après récupération du fichier (par ex. depuis SharePoint).
