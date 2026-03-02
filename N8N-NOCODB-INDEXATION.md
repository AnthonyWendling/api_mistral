# n8n : indexation NocoDB → API Mistral (guide pas à pas)

Guide **n8n** pour déclencher l’indexation des documents NocoDB dans les collections de l’API (webhook à l’enregistrement ou workflow planifié).

---

## Prérequis

- **n8n** avec accès à ton instance (self-hosted ou cloud).
- **Credential NocoDB** configurée dans n8n (URL de l’API + token).
- **API Mistral** déployée (ex. `https://apimistral-production.up.railway.app`).
- Une **collection** déjà créée (ex. `nocodb-documents`) ou l’id de la collection cible.

---

## Workflow 1 : Indexation à l’enregistrement (webhook NocoDB)

Dès qu’un enregistrement est créé (ou mis à jour) dans NocoDB, le webhook appelle n8n → récupération du fichier → indexation.

### Étape 1 : Créer le webhook dans n8n

1. Nouveau workflow.
2. Ajouter un nœud **Webhook**.
   - **HTTP Method** : POST.
   - **Path** : `nocodb-index` (ou autre). L’URL finale sera du type :  
     `https://ton-n8n.com/webhook/nocodb-index` (ou `.../webhook-test/...` en mode test).
   - **Response Mode** : selon ton besoin (ex. « When Last Node Finishes » pour renvoyer la réponse de l’API).
3. **Sauvegarder** et **activer** le workflow pour obtenir l’URL de production.

### Étape 2 : Préparer les données (optionnel)

Si le body NocoDB est imbriqué (ex. `body.data` ou `body.record`), ajouter un nœud **Set** ou **Code** pour aplatir et renommer les champs. Exemple avec **Set** (ajuster les noms selon ton webhook NocoDB) :

- `record_id` → `{{ $json.body?.Id ?? $json.body?.id ?? $json.Id ?? $json.id }}`
- `file_url` → `{{ $json.body?.Attachment ?? $json.body?.FileUrl ?? $json.Attachment ?? $json.file_url }}`
- `table_name` → `{{ $json.body?.TableName ?? $json.TableName ?? "Documents" }}`
- `base_id` → `{{ $json.body?.BaseId ?? $json.BaseId ?? "" }}`
- `collection_id` → `nocodb-documents` (ou une expression si tu varies par table)

Si NocoDB envoie directement les champs à la racine du body, tu peux utiliser `$json.body` dans les nœuds suivants (ex. `$json.body.id`).

### Étape 3 : Récupérer le fichier

**Cas A – NocoDB envoie une URL de fichier (recommandé)**

- Ajouter un nœud **HTTP Request**.
  - **Method** : GET.
  - **URL** : `{{ $json.file_url ?? $json.body?.Attachment ?? $json.body?.FileUrl }}`
  - **Response Format** : File (pour avoir le binaire en sortie).
- La sortie aura une **propriété binaire** (ex. `data`). Noter son nom pour l’étape 4.

**Cas B – Pas d’URL : récupérer la pièce jointe via l’API NocoDB**

- Utiliser le nœud **NocoDB** (ou **HTTP Request** vers l’API NocoDB) pour récupérer l’enregistrement et/ou l’URL de la pièce jointe, puis un **HTTP Request** GET sur cette URL comme en Cas A.
- Ou, si NocoDB fournit une URL signée dans le webhook, l’utiliser directement.

**Cas C – Envoyer l’URL à l’API sans télécharger dans n8n**

- Pas de nœud de téléchargement : tu passes directement à l’étape 4 et tu envoies `file_url` en form (voir ci-dessous).

### Étape 4 : Appeler l’API d’indexation

Ajouter un nœud **HTTP Request**.

- **Method** : POST.
- **URL** :  
  `https://apimistral-production.up.railway.app/vectors/collections/{{ $('Set').first().json.collection_id ?? 'nocodb-documents' }}/index`  
  (remplace `Set` par le nom de ton nœud qui définit `collection_id`, ou mets une valeur fixe comme `nocodb-documents`).

- **Send Body** : Oui.
- **Body Content Type** : **Multipart-Form** (si tu envoies un fichier binaire) **ou** **Form-Data** (si tu envoies seulement `file_url`).

**Si tu as un fichier binaire (Cas A ou B)** :

| Name     | Type         | Value / Expression |
|----------|--------------|--------------------|
| `file`   | Binary Data  | Binary Property = `data` (ou le nom de la propriété binaire du nœud précédent) |
| `document_id` | String | `{{ $('Set').first().json.record_id ?? $json.body?.Id ?? $json.body?.id }}` |
| `nocodb_record_id` | String | même expression que `document_id` |
| `nocodb_table_name` | String | `{{ $('Set').first().json.table_name ?? 'Documents' }}` |
| `nocodb_base_id` | String | `{{ $('Set').first().json.base_id ?? '' }}` |

**Si tu envoies seulement une URL (Cas C)** :

| Name     | Type  | Value / Expression |
|----------|-------|--------------------|
| `file_url` | String | `{{ $json.file_url ?? $json.body?.Attachment ?? $json.body?.FileUrl }}` |
| `document_id` | String | `{{ $json.body?.Id ?? $json.body?.id }}` |
| `nocodb_record_id` | String | même que `document_id` |
| `nocodb_table_name` | String | `{{ $json.body?.TableName ?? 'Documents' }}` |
| `nocodb_base_id` | String | `{{ $json.body?.BaseId ?? '' }}` |

- Sur ce nœud : activer **Continue On Fail** pour ne pas faire échouer le workflow si un fichier est non supporté ou trop gros.

### Étape 5 : Réponse (optionnel)

Si tu veux renvoyer un JSON au webhook (ex. pour NocoDB ou un autre appelant) : ajouter un nœud **Respond to Webhook** (ou laisser n8n répondre avec la sortie du dernier nœud). Le nœud Webhook en « When Last Node Finishes » renverra la réponse de l’API (ex. `{ "indexed_chunks": 8 }`).

---

## Workflow 2 : Indexation planifiée (ex. tous les jours)

Workflow déclenché par un **Schedule** qui liste les enregistrements NocoDB, filtre les nouveaux ou non indexés, puis appelle l’API d’indexation pour chacun.

### Étape 1 : Déclencheur

- Nœud **Schedule Trigger**.
  - **Rule** : ex. « Every day at 6:00 AM » (ou « Every 12 hours »).

### Étape 2 : Récupérer les enregistrements NocoDB

- Nœud **NocoDB**.
  - **Operation** : Get Many (ou équivalent pour lister les lignes).
  - **Base** / **Table** : ta base et la table qui contient les documents.
  - **Options** : si l’API le permet, ajouter un filtre (ex. `where (Indexed, eq, false)` ou `where (UpdatedAt, gte, dernière_date)`). Sinon, filtrer en n8n à l’étape suivante.

### Étape 3 : Filtrer les enregistrements à indexer (optionnel)

- Nœud **Filter** ou **IF** :
  - Ex. garder les items où `Indexed` est vide/false, ou où `UpdatedAt` > dernière exécution (stockée en variable ou en fichier/store).
- Pour « dernière date » : tu peux utiliser un nœud **Set** en début de workflow qui lit une variable (ex. `lastRun`) puis, après l’indexation, un nœud qui met à jour cette variable (ex. avec **Code** ou un store externe).

### Étape 4 : Pour chaque enregistrement – récupérer le fichier

- **Loop Over Items** (ou le flux n8n qui itère sur chaque item).
- Pour chaque item : récupérer l’URL du document (champ pièce jointe ou URL) puis :
  - soit **HTTP Request** GET (Response Format: File) pour avoir le binaire,
  - soit garder l’URL pour l’envoyer en `file_url` à l’API.

### Étape 5 : Appeler l’API d’indexation

- Nœud **HTTP Request** (comme dans le Workflow 1, étape 4) :
  - URL : `https://apimistral-production.up.railway.app/vectors/collections/nocodb-documents/index`
  - Body Multipart ou Form selon que tu envoies `file` (binaire) ou `file_url`.
  - Champs : `document_id`, `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id` (avec les champs de l’item courant, ex. `$json.Id`, `$json.TableName`).
  - **Continue On Fail** : activé.

### Étape 6 (optionnel) : Marquer comme indexé dans NocoDB

- Nœud **NocoDB** – **Update** : mettre à jour l’enregistrement (ex. champ `Indexed` = true ou `IndexedAt` = maintenant) pour ne pas le ré-indexer au prochain run.

---

## Configurer le webhook dans NocoDB

1. Table NocoDB qui contient les documents → **Automation** / **Webhooks**.
2. Nouveau webhook :
   - **Trigger** : **After Insert** (et éventuellement **After Update**).
   - **Action** : HTTP Request.
   - **URL** : `https://ton-n8n.com/webhook/nocodb-index` (remplacer par ton URL n8n).
   - **Method** : POST.
   - **Body** (JSON) : envoyer au minimum l’id du record et l’URL du fichier (ou l’identifiant de la pièce jointe). Exemple avec des placeholders NocoDB (à adapter à ta version) :
     - `{ "id": "{{ record.Id }}", "Attachment": "{{ record.Attachment }}", "TableName": "Documents", "BaseId": "..." }`
3. Sauvegarder. À chaque création (et optionnellement mise à jour), NocoDB enverra ce body à n8n.

---

## Recherche puis ouverture du record NocoDB (workflow séparé)

Une fois les documents indexés avec `nocodb_record_id`, etc. :

1. **Déclencheur** : Webhook ou formulaire avec une **query** et un **collection_id**.
2. **HTTP Request** :  
   POST `https://apimistral-production.up.railway.app/webhooks/search-documents`  
   Body JSON : `{ "query": "{{ $json.query }}", "collection_id": "{{ $json.collection_id }}", "top_k": 10 }`
3. La réponse contient **`documents`** avec pour chaque document : `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`, `source_file`, `file_url`.
4. Utiliser **`documents[0].nocodb_record_id`** (et table/base) pour :
   - construire l’URL NocoDB du record (ex. `https://ton-nocodb.com/nc/base_id/table_id/record_id`),
   - ou appeler l’API NocoDB (Get avec l’id) pour afficher le détail.

---

## Récap des expressions n8n utiles

| Donnée | Expression type (à adapter aux noms de champs) |
|--------|------------------------------------------------|
| Id record (depuis webhook body) | `{{ $json.body?.Id ?? $json.body?.id }}` |
| URL du fichier | `{{ $json.body?.Attachment ?? $json.body?.FileUrl ?? $json.file_url }}` |
| Nom de table | `{{ $json.body?.TableName ?? $json.TableName ?? 'Documents' }}` |
| Id base | `{{ $json.body?.BaseId ?? $json.BaseId ?? '' }}` |
| Collection cible | `nocodb-documents` ou `{{ $json.collection_id }}` |

---

## Référence API (rappel)

- **Indexation** : `POST /vectors/collections/{collection_id}/index`  
  Body (multipart) : `file` ou `file_url`, `document_id`, `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`.
- **Recherche** : `POST /webhooks/search-documents`  
  Body JSON : `{ "query": "...", "collection_id": "...", "top_k": 10 }`  
  Réponse : `results` (chunks) + `documents` (avec `nocodb_record_id`, etc.).

Voir **GUIDE-NOCODB-INDEXATION.md** pour la vue d’ensemble et **DOCUMENTATION.md** pour tous les endpoints.
