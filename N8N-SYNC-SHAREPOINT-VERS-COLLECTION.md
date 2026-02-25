# Remplir les collections avec les données SharePoint existantes (historique complet)

Ce guide décrit le **bon ordre** : d’abord **récupérer tous les dossiers** SharePoint, faire **définir par l’IA les meilleures collections** à avoir dans l’API pour qu’elle apprenne bien, puis **créer ces collections** et **les remplir** avec les fichiers.

---

## Ordre global (2 phases)

1. **Phase 1 – Dossiers → IA → collections**  
   Récupérer **tous les dossiers** SharePoint → envoyer la liste à l’API → l’**IA propose** les meilleures collections (nom, description, quels dossiers y affecter) → tu **crées** ces collections dans l’API.
2. **Phase 2 – Remplir chaque collection**  
   Pour chaque collection (et les dossiers qui lui sont associés), lister les **fichiers** dans ces dossiers → télécharger → envoyer à l’API pour indexation (avec métadonnées SharePoint).

---

## Phase 1 : Récupérer les dossiers SharePoint et faire définir les collections par l’IA

### 1.1 Récupérer tous les dossiers SharePoint (n8n)

- **Déclencheur** : Webhook (POST) ou Manual Trigger.
- **Microsoft OneDrive / SharePoint** :  
  - Opération pour **lister les dossiers** (et éventuellement sous-dossiers) de ta bibliothèque.  
  - Ex. : **List folder contents** sur la racine « Documents », en incluant les sous-dossiers si l’option existe, ou enchaîner plusieurs appels (racine puis chaque sous-dossier).  
- En sortie tu obtiens des items avec au moins : **path** (ou équivalent), **name** (nom du dossier), et éventuellement **id**.

Tu dois obtenir **un item par dossier** (pas encore les fichiers à l’intérieur), avec par exemple :
- `path` ou `parentReference.path` + `name`  
Adapte selon la structure réelle de ton nœud Microsoft.

### 1.2 Préparer la liste pour l’API (adapter à ta sortie « List get many »)

La sortie Microsoft **List get many** ressemble souvent à ceci (sans champ `path`) :

```json
{
  "id": "e41d4268-2801-47b7-847f-002e76995521",
  "name": "Restore_0300 COBOTSERV_20250401_172936",
  "displayName": "Restore_0300 COBOTSERV_20250401_172936",
  "webUrl": "https://drbmea.sharepoint.com/teams/Affaires/Restore_0300%20COBOTSERV_20250401_172936"
}
```

L’API **suggest-collections** accepte ce format. Chaque élément du tableau `folders` peut avoir :

- **`name`** (obligatoire) : utilise `displayName` ou `name`.
- **`webUrl`** (optionnel) : l’API en déduit un chemin pour l’IA.
- **`id`** (optionnel) : identifiant SharePoint.
- **`path`** (optionnel) : si tu as un vrai chemin, tu peux l’ajouter.

**Exemple de body à envoyer** (directement depuis les items « List get many ») :

```json
{
  "folders": [
    {
      "name": "Restore_0300 COBOTSERV_20250401_172936",
      "webUrl": "https://drbmea.sharepoint.com/teams/Affaires/Restore_0300%20COBOTSERV_20250401_172936",
      "id": "e41d4268-2801-47b7-847f-002e76995521"
    }
  ]
}
```

**Dans n8n**, deux options :

- **Option A – Un item par dossier, puis agrégation**  
  Après le nœud Microsoft (List get many), ajoute un nœud **Code** qui construit le tableau `folders` à partir de tous les items, puis un **HTTP Request** qui envoie ce tableau :
  ```javascript
  const folders = $input.all().map(i => ({
    name: i.json.displayName || i.json.name,
    webUrl: i.json.webUrl,
    id: i.json.id
  }));
  return [{ json: { folders } }];
  ```
  Puis **HTTP Request** : URL = `.../webhooks/suggest-collections`, Body = JSON, et dans le body utilise `{{ $json.folders }}` (ou envoie tout `$json` si ta structure est `{ folders: [...] }`).

- **Option B – Item unique avec tableau**  
  Avec un nœud **Aggregate** ou **Merge** qui regroupe tous les items en un seul contenant un tableau, construis un objet `{ "folders": [ ... ] }` où chaque élément a au moins `name`, et si possible `webUrl` et `id`, puis envoie-le en body du **HTTP Request**.

### 1.3 Appeler le webhook « suggest-collections »

- **HTTP Request** :  
  - **Method** : POST  
  - **URL** : `https://apimistral-production.up.railway.app/webhooks/suggest-collections`  
  - **Body** (JSON) :
    ```json
    {
      "folders": [
        { "path": "/Documents/Affaires", "name": "Affaires" },
        { "path": "/Documents/Contrats", "name": "Contrats" }
      ]
    }
    ```
  - Le champ **`folders`** doit contenir **tous** les dossiers récupérés à l’étape 1.1 (path + name pour chaque dossier).

La réponse de l’API contient :
- **`suggestion`** : texte brut de l’IA (explication + éventuel JSON).
- **`collections`** : si l’IA a renvoyé du JSON valide, tableau proposé du type :
  ```json
  [
    {
      "name": "affaires-commerciales",
      "description": "Contenus liés aux affaires et ventes.",
      "folder_paths": ["/Documents/Affaires", "/Documents/Ventes"]
    },
    {
      "name": "contrats",
      "description": "Contrats et juridique.",
      "folder_paths": ["/Documents/Contrats"]
    }
  ]
  ```
  Chaque objet = une **collection à créer** dans l’API, avec les **dossiers** à y associer.

### 1.4 Créer les collections dans l’API

- Pour **chaque** élément de **`collections`** (ou chaque ligne de la suggestion si tu pars à la main) :  
  **HTTP Request** → POST `https://apimistral-production.up.railway.app/vectors/collections`  
  → Body JSON : `{ "name": "nom-collection" }` (ex. `affaires-commerciales`, `contrats`).  
- Tu peux faire une **Boucle** (Loop) sur `$json.collections` et appeler POST `/vectors/collections` avec `{{ $json.name }}`.

À la fin de la Phase 1 : toutes les **collections recommandées par l’IA** existent dans l’API. Tu as aussi la **correspondance** dossier → collection (via `folder_paths`).

---

## Phase 2 : Remplir chaque collection avec les fichiers SharePoint

Une fois les collections créées, tu remplis chacune avec les **fichiers** des dossiers qui lui sont associés (selon la sortie de suggest-collections).

### Étape 2.0 : Partir de la sortie « suggest-collections »

- Tu peux enchaîner un second workflow qui reçoit en entrée le résultat de Phase 1 (liste des collections + `folder_paths`), ou relancer manuellement en lisant la suggestion.
- Pour **chaque** collection et **chaque** `folder_path` dans `folder_paths` : lister les fichiers de ce dossier → télécharger → indexer dans **cette** collection (voir ci‑dessous).

### Étape 2.1 : Créer la collection (déjà fait en Phase 1)

Les collections sont déjà créées en Phase 1. Tu utilises leur **id** (ex. `affaires-commerciales`) comme **`COLLECTION_ID`** pour l’indexation.

---

Pour **une** collection donnée (et un ou plusieurs dossiers `folder_paths`), le workflow suivant remplit cette collection.

### 2.1 Déclencher le workflow (webhook ou manuel)

**Option A – Webhook (lancer la synchro à la demande)**  
- Ajoute un nœud **Webhook** en premier.  
- Méthode : **POST** (ou GET si tu préfères).  
- Dans **Production** n8n, active le workflow pour avoir une URL du type :  
  `https://ton-n8n.com/webhook/xxx`  
- Quand tu appelles cette URL (navigateur, Power Automate, autre outil), le workflow se lance. Tu peux optionnellement envoyer en body JSON :  
  `{"collection_id": "historique-affaires", "folder_path": "/Documents"}` pour paramétrer la synchro.

**Option B – Déclencheur manuel**  
- Utilise un **Manual Trigger**. Tu lances le workflow à la main dans n8n (Execute Workflow).

**Option C – Planifié**  
- Utilise un **Schedule Trigger** (ex. tous les lundis à 6h) pour ré‑indexer régulièrement.

---

### 2.2 Récupérer les paramètres (si webhook avec body)

Si tu utilises un webhook avec un body JSON (collection_id, folder_path) :  
- Le premier nœud (Webhook) sort déjà `body.collection_id`, `body.folder_path`.  
- Sinon, ajoute un nœud **Set** pour définir des valeurs fixes :  
  - `collection_id` = `historique-affaires`  
  - `folder_path` = chemin du dossier SharePoint à scanner (ex. `/Documents` ou laisser vide pour la racine).

Tu utiliseras `{{ $json.collection_id }}` et éventuellement `{{ $json.folder_path }}` dans les nœuds suivants.

---

### 2.3 Lister tous les fichiers SharePoint (dossier cible)

- Ajoute un nœud **Microsoft OneDrive** (ou **Microsoft SharePoint**, selon ta version n8n).  
- **Operation** : du type **List** / **Get folder contents** / **List files in folder**.  
- Configure :  
  - **Site** / **Drive** : ton site SharePoint et la bibliothèque de documents.  
  - **Folder** : le dossier à scanner (ex. racine « Documents » ou un sous-dossier). Utilise `{{ $json.folder_path }}` si tu l’as passé par le webhook.  
- Si le nœud le permet, active l’option pour **inclure les sous-dossiers** (récursif), sinon tu devras soit répéter le workflow pour plusieurs dossiers, soit enchaîner plusieurs nœuds List.

En sortie : **un item par fichier** (et éventuellement par dossier). Chaque item a en général :  
`id`, `name`, `parentReference` (driveId, path, siteId), etc.

---

### 2.4 Filtrer uniquement les fichiers (optionnel)

- Les dossiers ont souvent un champ `folder` ou pas de `file`.  
- Ajoute un nœud **IF** ou **Filter** : garde seulement les items où `file` est présent (ou où `name` contient une extension .pdf, .docx, etc.).  
- Comme ça, tu n’envoies à l’API que des **fichiers**, pas des dossiers.

---

### 2.5 Télécharger chaque fichier depuis SharePoint

- Ajoute un nœud **Microsoft OneDrive** (ou SharePoint).  
- **Operation** : **Download** (ou « Get file content »).  
- **File identifier** : `{{ $json.id }}` (l’id de l’item courant).  
- Si le nœud demande **Drive ID** : `{{ $json.parentReference.driveId }}`.  

En sortie : le même item **avec une propriété binaire** (ex. `data`) contenant le fichier. Les métadonnées (id, name, parentReference) restent disponibles.

---

### 2.6 Envoyer le fichier à l’API pour indexation

- Ajoute un nœud **HTTP Request**.  
- **Method** : **POST**.  
- **URL** :  
  `https://apimistral-production.up.railway.app/vectors/collections/{{ $('Webhook').first().json.body?.collection_id || 'historique-affaires' }}/index`  
  (ou utilise un nœud Set en amont pour mettre `collection_id` dans l’item et ici `{{ $json.collection_id }}` si tu l’as propagé).  
- **Send Body** : Oui.  
- **Body Content Type** : **Multipart-Form**.  
- **Parameters** :  
  - `file` : **Binary Data**, Binary Property = `data` (ou le nom de ta propriété binaire).  
  - `document_id` : `{{ $json.id }}` (id SharePoint, pour déduplication).  
  - `sharepoint_item_id` : `{{ $json.id }}`.  
  - `drive_id` : `{{ $json.parentReference.driveId }}`.  
  - `folder_path` : `{{ $json.parentReference.path }}` (ou chemin du dossier parent).  
  - `site_id` : `{{ $json.parentReference.siteId }}` (si présent).

Comme ça, chaque fichier est indexé **avec** les infos SharePoint pour pouvoir le retrouver plus tard (search-documents → bon dossier / bon fichier).

---

### 2.7 Gérer les erreurs (recommandé)

- Certains fichiers peuvent échouer (type non supporté, trop gros, etc.).  
- Pour **ne pas tout arrêter** : active sur le nœud HTTP Request l’option **Continue On Fail** (continuer en cas d’erreur).  
- Optionnel : en aval, un nœud **IF** sur `$json.error` pour envoyer les échecs vers un log ou une notification.

---

## Résumé du flux complet

**Phase 1 – Définir les collections avec l’IA**
```
[Webhook ou Manual Trigger]
         ↓
[Microsoft OneDrive : Lister tous les DOSSIERS (pas les fichiers) du SharePoint]
         ↓
[Code / Set : construire { "folders": [ { "path", "name" }, ... ] }]
         ↓
[HTTP Request : POST .../webhooks/suggest-collections  avec body.folders]
         ↓
[Pour chaque élément de response.collections]
   → HTTP Request : POST .../vectors/collections  avec { "name": "..." }
```

**Phase 2 – Remplir chaque collection**
```
[Pour chaque collection et chaque folder_path associé]
         ↓
[Microsoft OneDrive : List folder contents (fichiers du dossier)]
         ↓
[Filter : garder seulement les fichiers]
         ↓
[Microsoft OneDrive : Download file (id = $json.id)]
         ↓
[HTTP Request : POST .../vectors/collections/COLLECTION_ID/index
   file = Binary, document_id + sharepoint_item_id + drive_id + folder_path + site_id]
```

---

## Points importants

1. **Collection** : même `collection_id` pour toute la synchro (ex. `historique-affaires`) pour avoir un seul historique.
2. **Déduplication** : en envoyant `document_id` = id SharePoint, tu évites de ré‑indexer deux fois le même fichier si tu relances le workflow.
3. **Types de fichiers** : l’API gère PDF, Word, Excel, PPTX, images (OCR). Les autres types renverront une erreur ; avec « Continue On Fail » le workflow passera au fichier suivant.
4. **Volume** : si tu as beaucoup de fichiers, le workflow peut prendre du temps (un appel API par fichier). Tu peux limiter en filtrant par extension ou par dossier.
5. **Webhook** : une fois le workflow activé en production, l’URL du webhook sert à **lancer la synchro** quand tu veux (ex. « Remplir / mettre à jour l’historique des affaires »).

---

## Exemple de body pour le webhook (optionnel)

Pour déclencher la synchro avec des paramètres :

**POST** `https://ton-n8n.com/webhook/xxx`  
**Content-Type** : `application/json`  
**Body** :
```json
{
  "collection_id": "historique-affaires",
  "folder_path": "/Documents/Affaires"
}
```

Dans le workflow, tu récupères `$json.body.collection_id` et `$json.body.folder_path` (selon la structure de sortie du nœud Webhook) et tu les utilises dans les nœuds Microsoft OneDrive (folder) et HTTP Request (URL d’indexation).

---

En suivant ce guide, tu obtiens un **webhook** (ou un déclencheur manuel/planifié) qui **remplit tes collections** avec les données déjà présentes dans SharePoint et construit un **historique complet** exploitable par recherche vectorielle et RAG.
