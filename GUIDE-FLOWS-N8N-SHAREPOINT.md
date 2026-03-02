# Guide : indexer tout SharePoint puis aller chercher les fichiers dans le bon dossier (n8n)

Ce guide décrit **deux types de flows n8n** à mettre en place quand tes documents sont déjà sur SharePoint :

1. **Flow d’indexation** : indexer tous les fichiers d’un (ou plusieurs) dossier(s) SharePoint dans une collection de l’API → recherche vectorielle possible.
2. **Flow de recherche** : l’utilisateur pose une question → l’API trouve les bons documents → n8n va dans le **bon dossier SharePoint** les récupérer.

Condition importante : à l’indexation, tu envoies les **métadonnées SharePoint** (`sharepoint_item_id`, `drive_id`, `folder_path`, etc.) pour que la recherche renvoie de quoi cibler le bon fichier et le bon dossier.

---

## Vue d’ensemble

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FLOW 1 – INDEXATION (une fois ou planifié)                                  │
│  SharePoint (dossiers) → lister fichiers → télécharger chaque fichier        │
│  → POST /vectors/collections/{id}/index (file + sharepoint_item_id, etc.)     │
│  → Les documents sont dans une collection, avec les IDs SharePoint stockés   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  FLOW 2 – RECHERCHE + RÉCUPÉRATION (à la demande)                            │
│  Question (webhook/formulaire) → POST /webhooks/search-documents             │
│  → Réponse : documents avec sharepoint_item_id, drive_id, folder_path…        │
│  → n8n : Microsoft OneDrive/SharePoint → Download avec sharepoint_item_id    │
│  → Tu as le fichier du bon dossier SharePoint                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Indexer des fichiers dans des collections déjà créées

Tu as déjà les collections côté API (ex. `nestle-affaires`, `affaires-commerciales`, etc.). Pour les **remplir** avec des fichiers :

1. **Décider quel dossier SharePoint va dans quelle collection**  
   Exemple de correspondance (à adapter à ta structure) :

   | Collection (id) | Dossier SharePoint à indexer |
   |-----------------|-----------------------------|
   | `nestle-affaires` | Chemin du dossier Nestlé / Affaires dans ton site |
   | `affaires-commerciales` | Dossier « Affaires commerciales » |
   | `extensions-web` | Dossier « Extensions web » |
   | `documents-partages` | Dossier « Documents partagés » |
   | `terreos-affaires` | Dossier Terreos / Affaires |
   | `gestion-dossiers-clients` | Dossier gestion dossiers clients |
   | `evenements` | Dossier Événements |
   | `jacquet-affaires` | Dossier Jacquet / Affaires |
   | `restore-dossiers` | Dossier(s) Restore |
   | `coca-cola-partenaires` | Dossier Coca-Cola / Partenaires |
   | `test` | Un dossier de test |

2. **Utiliser un seul flow n8n** avec **webhook ou Manual Trigger** qui reçoit :
   - `collection_id` : l’id de la collection (ex. `nestle-affaires`)
   - `folder_path` : le chemin du dossier SharePoint à scanner (ou l’ID du dossier si ton nœud Microsoft le demande)

3. **Dans le flow** :  
   → Lister les fichiers du dossier SharePoint (`folder_path`)  
   → Pour chaque fichier : Download  
   → **POST** `https://apimistral-production.up.railway.app/vectors/collections/{{ collection_id }}/index` avec le fichier en binaire + `document_id`, `sharepoint_item_id`, `drive_id`, `folder_path`, `site_id` (voir Flow 1 ci‑dessous).

4. **Lancer l’indexation** :  
   - Soit une fois par collection (en envoyant `collection_id` + `folder_path` au webhook),  
   - Soit un flow qui boucle sur une liste de paires (collection_id, folder_path) et exécute le même enchaînement pour chaque paire.

**Exemple d’appel webhook pour indexer une collection :**

```json
POST https://ton-n8n.com/webhook/xxx
Content-Type: application/json

{
  "collection_id": "nestle-affaires",
  "folder_path": "/sites/MonSite/Documents partagés/Nestlé/Affaires"
}
```

Le flow n8n lit `collection_id` et `folder_path`, liste les fichiers de ce dossier, les télécharge, et envoie chaque fichier à `POST .../vectors/collections/nestle-affaires/index`. Tu répètes pour chaque collection en changeant `collection_id` et `folder_path`.

---

## Indexer tout un site SharePoint (approche « sitemap »)

Tu veux **indexer tout le contenu** d’un site ou d’une bibliothèque SharePoint (tous les dossiers et sous-dossiers), sans avoir à lister chaque dossier à la main.

### Limitation Microsoft Graph

Il **n’existe pas** d’endpoint du type « donne-moi tous les fichiers du site en un coup ». Il faut **parcourir l’arborescence** :

1. Lister les **enfants** de la racine du drive : `GET /sites/{site-id}/drive/root/children`
2. Pour chaque item : si c’est un **dossier** (`folder` présent), rappeler **children** sur ce dossier
3. Répéter jusqu’à n’avoir plus que des **fichiers**
4. Tu obtiens une liste plate de tous les fichiers → ensuite : télécharger chaque fichier et l’envoyer à l’API d’indexation

C’est l’équivalent d’un **sitemap** : on construit la carte complète du drive (dossiers + fichiers), puis on indexe chaque fichier.

### Comment faire dans n8n

**Option 1 – Workflow récursif (Loop + sous-workflow)**  
- Un workflow qui liste les enfants de la racine (ou d’un dossier passé en paramètre).  
- Pour chaque item :  
  - Si **fichier** → Download → POST index (avec `collection_id` unique, ex. `sharepoint-complet`, et les métadonnées SharePoint).  
  - Si **dossier** → appeler un **sous-workflow** (ou le même workflow) qui liste les enfants de ce dossier et refait la même logique.  
- En n8n : utiliser **Execute Workflow** pour la récursion, ou **Loop Over Items** en gardant une queue de dossiers à traiter.

**Option 2 – Code node + Graph API (liste plate de tous les fichiers)**  
- Un nœud **Code** (JavaScript) qui utilise **$http** (ou un nœud HTTP Request avec auth OAuth2 Microsoft) pour :  
  - Appeler `GET /sites/{site-id}/drive/root/children`  
  - Pour chaque enfant de type dossier, appeler `/drive/items/{folder-id}/children` et accumuler les dossiers à traiter  
  - Jusqu’à ce que la queue soit vide, en collectant tous les **fichiers** (items qui ont une propriété `file`)  
- En sortie du Code : un tableau d’items (un par fichier) avec `id`, `name`, `parentReference`, etc.  
- Ensuite : **Loop** sur ce tableau → pour chaque item, **Microsoft OneDrive : Download** → **HTTP Request** vers `POST .../vectors/collections/{collection_id}/index` avec les métadonnées SharePoint.

**Option 3 – Plusieurs étages de « List folder »**  
- Si ta structure n’a pas trop de niveaux :  
  - Nœud 1 : List folder contents sur la racine.  
  - Nœud 2 : Pour chaque item, si dossier → List folder contents sur ce dossier (en chaînant les nœuds ou en dupliquant le flux).  
  - Répéter sur 2–3 niveaux, puis filtrer les fichiers et envoyer à l’index.  
- Moins flexible qu’une vraie récursion mais possible sans Code.

### Où envoyer les fichiers indexés ?

- **Une seule collection** (ex. `sharepoint-complet`) : tous les fichiers du site vont dans cette collection. Les métadonnées `folder_path`, `sharepoint_item_id`, etc. permettent quand même de retrouver le bon dossier/fichier lors de la recherche.  
- **Mapping chemin → collection** : selon le chemin du fichier (ex. tout ce qui contient `/Nestlé/Affaires` → collection `nestle-affaires`), tu choisis le `collection_id` avant d’appeler l’API. Tu peux faire ce mapping dans un nœud **Code** ou **IF** après avoir listé les fichiers.

### Mapping chemin → collection_id (nœud Code ou IF)

Après avoir listé/téléchargé les fichiers (chaque item a un `parentReference.path` ou un `folder_path`), tu ajoutes un nœud qui détermine **collection_id** en fonction du chemin, puis tu utilises ce `collection_id` dans l’URL du POST index.

#### Avec un nœud Code (recommandé)

Place le nœud **Code** juste après le nœud qui fournit les items (liste de fichiers ou sortie Download). Chaque item doit avoir au moins le chemin du dossier parent (ex. `parentReference.path` ou un champ que tu mets à jour).

**Entrée** : un item par fichier, avec par ex. `json.parentReference.path` = `"/drive/root:/Documents partagés/Nestlé/Affaires"` ou un chemin similaire.

**Sortie** : le même item avec en plus `json.collection_id` = l’id de la collection à utiliser.

Exemple de code (à coller dans le nœud Code, et à adapter aux chemins réels de ton SharePoint) :

```javascript
// Mapping : partie du chemin (minuscules) → id de collection
const PATH_TO_COLLECTION = {
  "nestlé/affaires": "nestle-affaires",
  "nestle/affaires": "nestle-affaires",
  "affaires-commerciales": "affaires-commerciales",
  "extensions-web": "extensions-web",
  "documents-partages": "documents-partages",
  "terreos/affaires": "terreos-affaires",
  "terreos-affaires": "terreos-affaires",
  "gestion-dossiers-clients": "gestion-dossiers-clients",
  "evenements": "evenements",
  "jacquet/affaires": "jacquet-affaires",
  "jacquet-affaires": "jacquet-affaires",
  "restore": "restore-dossiers",
  "coca-cola": "coca-cola-partenaires",
  "coca cola": "coca-cola-partenaires",
  "test": "test",
};

function getCollectionId(path) {
  if (!path || typeof path !== "string") return "documents-partages";
  const pathLower = path.toLowerCase().replace(/\\/g, "/");
  for (const [key, collectionId] of Object.entries(PATH_TO_COLLECTION)) {
    if (pathLower.includes(key)) return collectionId;
  }
  return "documents-partages"; // collection par défaut
}

const items = $input.all();
return items.map((item) => {
  const path = item.json.parentReference?.path ?? item.json.folder_path ?? "";
  const collection_id = getCollectionId(path);
  return { json: { ...item.json, collection_id } };
});
```

- Adapte les clés de `PATH_TO_COLLECTION` aux segments de chemin que tu as vraiment (noms de dossiers, avec ou sans accents).
- La collection par défaut (ici `documents-partages`) est utilisée si aucun motif ne correspond.

Ensuite, dans le nœud **HTTP Request** d’indexation, utilise :

- **URL** : `https://apimistral-production.up.railway.app/vectors/collections/{{ $json.collection_id }}/index`

Comme ça, chaque fichier est envoyé dans la bonne collection selon son chemin.

#### Avec des nœuds IF (quelques collections seulement)

Si tu n’as que 2–3 collections et des chemins faciles à tester :

1. **IF** : condition `{{ $json.parentReference.path.includes('Nestlé') || $json.parentReference.path.includes('nestle') }}` (ou équivalent) → **true** : aller vers un nœud **Set** qui met `collection_id` = `nestle-affaires`, puis vers l’index.
2. **false** : deuxième **IF** pour un autre motif (ex. `affaires-commerciales`) → Set → index.
3. Répéter ou terminer par un **Set** par défaut (`documents-partages`) puis index.

C’est plus verbeux qu’un Code dès qu’il y a plus de 2–3 collections ; le nœud Code reste plus simple à maintenir.

---

### Endpoints Graph utiles

| Action | Endpoint |
|--------|----------|
| Enfants de la racine du site | `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drive/root/children` |
| Enfants d’un dossier | `GET https://graph.microsoft.com/v1.0/sites/{site-id}/drive/items/{item-id}/children` |
| Pagination | Utiliser `@odata.nextLink` dans la réponse pour la suite des résultats. |

Droits nécessaires : `Sites.Read.All` ou `Files.Read.All` (selon le scope).

En résumé : **indexer tout le SharePoint** = parcourir récursivement l’arborescence (racine → dossiers → sous-dossiers) pour obtenir la liste de tous les fichiers, puis pour chaque fichier : Download → POST index avec métadonnées. Tu peux tout mettre dans une collection unique type « sitemap » ou répartir par chemin dans tes collections existantes.

---

## Flow 1 : Indexer tous les fichiers d’un dossier SharePoint

Objectif : **une collection** (ex. `mes-documents`) contient tous les fichiers indexés d’un dossier (ou de plusieurs), avec les infos pour les retrouver dans SharePoint.

### Option A : Une seule collection, un seul dossier à indexer

1. **Créer la collection** (une fois)  
   - **HTTP Request** : POST `https://apimistral-production.up.railway.app/vectors/collections`  
   - Body JSON : `{ "name": "mes-documents" }`  
   - Tu obtiens un `id` (ex. `mes-documents`). C’est ton `collection_id`.

2. **Déclencheur**  
   - Webhook (POST avec body optionnel `{"collection_id": "mes-documents", "folder_path": "/Documents/MonDossier"}`)  
   - ou **Manual Trigger**  
   - ou **Schedule** (ex. tous les lundis) pour ré-indexer.

3. **Récupérer le dossier à scanner**  
   - Si webhook avec body : `collection_id` et éventuellement `folder_path` viennent de `$json.body`.  
   - Sinon : nœud **Set** avec `collection_id` = `mes-documents` et `folder_path` = chemin du dossier SharePoint (ex. racine ou `/Documents/Affaires`).

4. **Lister les fichiers du dossier SharePoint**  
   - Nœud **Microsoft OneDrive** ou **Microsoft SharePoint**.  
   - Opération : **List folder contents** / **Get folder contents**.  
   - Site/Drive : ton site et ta bibliothèque.  
   - Folder : `{{ $json.folder_path }}` ou la valeur définie.  
   - Sortie : un item par fichier (et éventuellement sous-dossier) avec `id`, `name`, `parentReference` (driveId, path, siteId).

5. **Filtrer uniquement les fichiers** (optionnel)  
   - Nœud **IF** ou **Filter** : garder les items qui ont une extension (`.pdf`, `.docx`, etc.) ou où `file` est présent, pour ne pas traiter les dossiers.

6. **Pour chaque fichier**  
   - **Microsoft OneDrive / SharePoint** : opération **Download**.  
   - File/Item ID : `{{ $json.id }}`.  
   - Drive ID si demandé : `{{ $json.parentReference.driveId }}`.  
   - En sortie : même item + donnée binaire (ex. propriété `data`).

7. **Envoyer à l’API pour indexation**  
   - **HTTP Request** :  
     - Method : **POST**  
     - URL : `https://apimistral-production.up.railway.app/vectors/collections/{{ $('Set').first().json.collection_id }}/index`  
       (ou `{{ $json.collection_id }}` si tu l’as propagé sur chaque item)  
     - Body : **Multipart Form**  
     - Champs :
       - `file` : **Binary Data**, Binary Property = `data` (ou le nom de ta propriété binaire)
       - `document_id` : `{{ $json.id }}` (id SharePoint = déduplication)
       - `sharepoint_item_id` : `{{ $json.id }}`
       - `drive_id` : `{{ $json.parentReference.driveId }}`
       - `folder_path` : `{{ $json.parentReference.path }}` (ou chemin du dossier parent)
       - `site_id` : `{{ $json.parentReference.siteId }}` (si présent)

8. **Gestion d’erreurs**  
   - Sur le nœud HTTP Request : activer **Continue On Fail** pour ne pas tout arrêter si un fichier échoue (type non supporté, etc.).

Résultat : tous les fichiers du dossier sont indexés dans la collection **avec** les métadonnées SharePoint. Tu pourras ensuite les retrouver par recherche vectorielle et aller les chercher dans le **bon dossier** avec Flow 2.

### Option B : Plusieurs dossiers → une ou plusieurs collections (avec suggestion IA)

Si tu veux que l’IA te propose des collections à partir de la structure des dossiers :

1. **Lister tous les dossiers** SharePoint (pas les fichiers) avec **Microsoft OneDrive / SharePoint** (List folders / List get many, etc.).
2. **Code** : construire `{ "folders": [ { "name", "webUrl", "id" }, ... ] }` à partir des items.
3. **HTTP Request** : POST `https://apimistral-production.up.railway.app/webhooks/suggest-collections` avec ce body.
4. Dans la réponse : `collections` (nom, description, `folder_paths`). Pour chaque collection proposée :
   - **HTTP Request** : POST `.../vectors/collections` avec `{ "name": "nom-collection" }`.
5. Pour **chaque** collection et **chaque** `folder_path` dans `folder_paths` : refaire les étapes 4 à 8 de l’option A (lister fichiers du dossier → download → index avec métadonnées SharePoint).

Détail pas à pas : **N8N-SYNC-SHAREPOINT-VERS-COLLECTION.md**.

---

## Flow 2 : Rechercher puis aller chercher le fichier dans le bon dossier SharePoint

Objectif : l’utilisateur envoie une **question** (ou un mot-clé) → l’API renvoie les documents pertinents **avec** `sharepoint_item_id`, `drive_id`, `folder_path` → n8n télécharge le fichier depuis le **bon dossier** SharePoint.

### Étapes

1. **Déclencheur**  
   - **Webhook** (POST, body JSON `{"query": "template mail Power Automate", "collection_id": "mes-documents"}`)  
   - ou **Formulaire** / **Bouton** qui envoie la question et le `collection_id`.

2. **Recherche vectorielle**  
   - **HTTP Request** :  
     - Method : **POST**  
     - URL : `https://apimistral-production.up.railway.app/webhooks/search-documents`  
     - Body JSON :
       ```json
       {
         "query": "{{ $json.query }}",
         "collection_id": "{{ $json.collection_id }}",
         "top_k": 10
       }
       ```
   - La réponse contient :
     - `results` : les chunks trouvés (texte + métadonnées).
     - `documents` : liste de documents **uniques** avec `document_id`, `source_file`, `file_url`, et si tu les as indexés : **`sharepoint_item_id`**, **`drive_id`**, **`folder_path`**, **`site_id`**.

3. **Prendre le document à récupérer**  
   - Souvent le **premier** document = le plus pertinent : `documents[0]`.  
   - Nœud **Set** ou **Code** : `doc = $json.documents[0]` pour avoir un seul item avec `sharepoint_item_id`, `drive_id`, etc.

4. **Télécharger depuis SharePoint (bon dossier, bon fichier)**  
   - Nœud **Microsoft OneDrive** ou **Microsoft SharePoint**.  
   - Opération : **Download** (ou Get file by ID).  
   - **Item ID** : `{{ $json.sharepoint_item_id }}` (ou `$json.documents[0].sharepoint_item_id` si tu n’as pas fait de Set).  
   - **Drive ID** (si le nœud le demande) : `{{ $json.drive_id }}`.  
   - Le nœud utilise ces IDs pour cibler le **bon fichier** dans le **bon drive/dossier** SharePoint.

5. **Utiliser le fichier**  
   - Le binaire est disponible (ex. propriété `data`). Tu peux : envoyer par email, stocker ailleurs, renvoyer au client, alimenter un autre workflow, etc.

### Schéma du flow 2

```
[Webhook / Formulaire : query + collection_id]
         ↓
[HTTP Request : POST /webhooks/search-documents]
         ↓
[Set ou Code : garder documents[0]]
         ↓
[Microsoft OneDrive/SharePoint : Download avec sharepoint_item_id (+ drive_id)]
         ↓
[Utilisation du fichier]
```

Si tu n’as **pas** stocké `sharepoint_item_id` à l’indexation, la réponse contient quand même `source_file` et `file_url` ; tu peux tenter d’utiliser `file_url` (si accessible) ou lister le dossier avec `folder_path` et filtrer par `source_file`. Pour un flux fiable, ré-indexer avec les métadonnées SharePoint (Flow 1).

---

## Récapitulatif des endpoints

| Action | Endpoint | Body / usage |
|--------|----------|--------------|
| Créer une collection | POST `/vectors/collections` | `{ "name": "ma-collection" }` |
| Indexer un fichier (avec métadonnées SharePoint) | POST `/vectors/collections/{collection_id}/index` | Multipart : `file`, `document_id`, `sharepoint_item_id`, `drive_id`, `folder_path`, `site_id` |
| Recherche + liste des documents pour SharePoint | POST `/webhooks/search-documents` | `{ "query": "...", "collection_id": "...", "top_k": 10 }` → `documents[]` avec `sharepoint_item_id`, `drive_id`, etc. |

---

## Points importants

- **Indexation (Flow 1)** : toujours envoyer **au minimum** `document_id` et **`sharepoint_item_id`** (et idéalement `drive_id`, `folder_path`, `site_id`) pour que Flow 2 puisse aller dans le **bon dossier** SharePoint et télécharger le bon fichier.
- **Déduplication** : `document_id` = id SharePoint évite d’indexer deux fois le même fichier si tu relances l’indexation.
- **Types de fichiers** : l’API gère PDF, Word, Excel, PPTX, images (OCR). Activer **Continue On Fail** sur l’indexation pour ignorer les fichiers non supportés.
- **Références détaillées** :  
  - Indexation complète + suggestion de collections : **N8N-SYNC-SHAREPOINT-VERS-COLLECTION.md**  
  - Détail recherche + champs métadonnées : **N8N-SHAREPOINT-RECHERCHE.md**

Avec ces deux flows, tu **indexes tout** depuis SharePoint dans une (ou plusieurs) collection(s), puis tu **crées des flows n8n** qui, à partir d’une question, vont **dans le bon dossier SharePoint** récupérer les bons fichiers.
