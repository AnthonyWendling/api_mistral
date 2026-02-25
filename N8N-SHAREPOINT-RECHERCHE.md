# n8n : retrouver le bon dossier et le bon fichier SharePoint

Ce guide décrit comment **indexer** des fichiers SharePoint avec les métadonnées nécessaires (dossier, item ID, drive, site), puis **rechercher** via une question et **récupérer le bon fichier** dans SharePoint (bon dossier, bon fichier).

---

## Principe

1. **À l’indexation** : quand tu envoies un fichier à l’API (depuis n8n, après l’avoir téléchargé depuis SharePoint), tu envoies aussi les **identifiants SharePoint** (item ID, chemin du dossier, drive, site). L’API les stocke avec les vecteurs.
2. **À la recherche** : tu envoies une **question** à l’API → elle retourne les documents les plus pertinents **avec** ces identifiants → dans n8n tu utilises le nœud **Microsoft SharePoint / OneDrive** pour télécharger le fichier avec l’**item ID** (ou le chemin).

Sans ces métadonnées, la recherche ne retourne que le nom du fichier et une URL souvent protégée ; avec elles, n8n peut appeler directement SharePoint pour récupérer le bon fichier.

---

## Partie 1 : Indexer avec les métadonnées SharePoint

Quand tu indexes un document qui vient de SharePoint, il faut envoyer à l’API les champs suivants (en plus de `file` ou `file_url`) pour pouvoir le retrouver plus tard.

### Champs optionnels (formulaire multipart)

| Champ | Description | Où le trouver dans n8n |
|-------|-------------|------------------------|
| `folder_path` | Chemin du dossier (ex. `/Documents/Projets 2025`) | Sortie du nœud Microsoft SharePoint : chemin du dossier parent ou `path` de l’item. |
| `sharepoint_item_id` | ID Graph de l’élément (fichier) | Sortie du nœud Microsoft OneDrive/SharePoint : champ `id` de l’item (driveItem). |
| `drive_id` | ID du lecteur (document library) | Sortie du nœud : `parentReference.driveId` ou champ `driveId`. |
| `site_id` | ID du site SharePoint | Sortie du nœud : `parentReference.siteId` ou configuration du site. |

Tu peux n’envoyer que ceux que tu utilises (souvent **`sharepoint_item_id`** suffit pour « Download by ID »).

### Workflow n8n : indexation avec métadonnées SharePoint

1. **Déclencheur** : Schedule, Webhook, ou « When a file is created » SharePoint (si disponible).
2. **Microsoft OneDrive** ou **Microsoft SharePoint** :  
   - Opération **List** ou **Get folder contents** pour lister les fichiers d’un dossier,  
   - ou **Download** d’un fichier précis.  
   La sortie contient en général : `id` (item id), `name`, `parentReference` (driveId, path), etc.
3. **Télécharger le fichier** (si pas déjà en binaire) : nœud **Microsoft OneDrive** → **Download** avec l’`id` de l’item → la sortie a une propriété binaire (ex. `data`).
4. **HTTP Request** vers l’API :
   - **Method** : POST  
   - **URL** : `https://apimistral-production.up.railway.app/vectors/collections/TA_COLLECTION/index`  
   - **Body** : Multipart-Form  
   - Champs :
     - `file` : Binary Data, propriété = `data` (ou le nom de ta propriété binaire)
     - `document_id` : `{{ $json.id }}` (id SharePoint de l’item)
     - `folder_path` : `{{ $json.parentReference.path }}` ou le chemin du dossier (selon la sortie du nœud)
     - `sharepoint_item_id` : `{{ $json.id }}`
     - `drive_id` : `{{ $json.parentReference.driveId }}`
     - `site_id` : `{{ $json.parentReference.siteId }}` (si présent)

Adapte les expressions (`$json.id`, `$json.parentReference.driveId`, etc.) à la **structure réelle** de la sortie de ton nœud Microsoft (vérifier dans l’aperçu de l’exécution).

---

## Partie 2 : Rechercher puis récupérer le bon fichier SharePoint

Objectif : l’utilisateur demande « le document sur le template mail Power Automate » → l’API trouve le bon document → n8n télécharge ce fichier depuis SharePoint.

### Workflow n8n : recherche + téléchargement

1. **Déclencheur** : Webhook (question utilisateur), formulaire, ou bouton.
2. **HTTP Request** – recherche :
   - **Method** : POST  
   - **URL** : `https://apimistral-production.up.railway.app/webhooks/search-documents`  
   - **Body** : JSON  
     ```json
     {
       "query": "{{ $json.question }}",
       "collection_id": "test-n8n",
       "top_k": 10
     }
     ```
3. La réponse contient **`documents`** : tableau de documents uniques avec `document_id`, `source_file`, `file_url`, et si tu les as indexés : **`folder_path`**, **`sharepoint_item_id`**, **`drive_id`**, **`site_id`**.
4. **Prendre le premier document** (le plus pertinent) :  
   - Soit avec un nœud **Set** qui garde `documents[0]`,  
   - soit les nœuds suivants utilisent directement `{{ $json.documents[0] }}`.
5. **Microsoft OneDrive** ou **Microsoft SharePoint** :
   - Opération **Download** (ou **Get file by ID** selon le nœud).
   - **Item ID** (ou équivalent) : `{{ $json.documents[0].sharepoint_item_id }}`  
     Si le nœud demande **Drive ID** et **Item ID** :  
     - Drive ID : `{{ $json.documents[0].drive_id }}`  
     - Item ID : `{{ $json.documents[0].sharepoint_item_id }}`  
   - Si tu n’as que **path** : utilise `{{ $json.documents[0].folder_path }}` + nom du fichier (`source_file`) selon ce que le nœud attend.

6. Le fichier téléchargé (binaire) peut être envoyé par email, stocké, ou renvoyé à l’utilisateur.

### Schéma du flux

```
[Webhook / Formulaire : question]
         ↓
[HTTP Request : POST /webhooks/search-documents  →  query + collection_id]
         ↓
[Optionnel : Set / Code pour ne garder que documents[0]]
         ↓
[Microsoft SharePoint / OneDrive : Download  avec sharepoint_item_id (et drive_id si besoin)]
         ↓
[Utilisation du fichier : envoi, stockage, etc.]
```

---

## Si tu n’as pas stocké sharepoint_item_id à l’indexation

- **search-documents** retourne quand même `source_file` et `file_url`. Tu peux :
  - utiliser **file_url** dans un HTTP Request (si l’URL est accessible avec auth depuis n8n),
  - ou **lister le dossier** SharePoint avec **folder_path** (si tu l’as stocké) puis filtrer par **source_file** pour retrouver le bon fichier.
- Pour les prochains documents : **ré-indexer en envoyant** `sharepoint_item_id` (et si possible `drive_id`, `folder_path`, `site_id`) pour pouvoir utiliser directement « Download by ID » et ainsi cibler le **bon dossier** et le **bon fichier** SharePoint.

---

## Résumé des champs API

**À l’indexation** (POST `/vectors/collections/{id}/index` ou POST `/analyze/document` avec `add_to_collection_id`) :

- `file` ou `file_url`, `document_id` (recommandé)
- **Optionnel** : `folder_path`, `sharepoint_item_id`, `drive_id`, `site_id`

**À la recherche** (POST `/webhooks/search-documents`) :

- Réponse : `results` (chunks) + **`documents`** avec pour chaque document :
  - `document_id`, `source_file`, `file_url`
  - et, si fournis à l’indexation : `folder_path`, `sharepoint_item_id`, `drive_id`, `site_id`

Utilise **`sharepoint_item_id`** (et **`drive_id`** si le nœud le demande) dans le nœud Microsoft SharePoint pour **chercher correctement le bon dossier et le bon fichier** et le télécharger.
