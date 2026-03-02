# n8n : indexation NocoDB → API Mistral (guide pas à pas)

Guide **n8n** pour déclencher l’indexation des documents NocoDB dans les collections de l’API (webhook à l’enregistrement ou workflow planifié).

---

## Prérequis

- **n8n** avec accès à ton instance (self-hosted ou cloud).
- **Credential NocoDB** configurée dans n8n (URL de l’API + token).
- **API Mistral** déployée (ex. `https://apimistral-production.up.railway.app`).
- Une **collection** déjà créée (ex. `nocodb-documents`) ou l’id de la collection cible.

---

## Données nécessaires pour l’indexation

Pour que l’indexation fonctionne (webhook ou workflow planifié), il faut que la **table NocoDB** et le **payload** fournissent les champs ci-dessous. Tu peux t’en servir comme checklist pour ta base.

### Colonnes à avoir dans la table NocoDB (documents)

| Colonne | Type NocoDB | Obligatoire | Rôle |
|--------|-------------|-------------|------|
| **Id** | (géré par NocoDB) | Oui | Identifiant unique de l’enregistrement. Utilisé comme `document_id` et `nocodb_record_id` pour l’API. |
| **Fichier / pièce jointe** | Attachment ou URL | Oui | Le document à indexer : soit une pièce jointe (Attachment), soit une URL de téléchargement (SingleLineText ou URL). L’API a besoin soit du fichier (binaire), soit de `file_url`. |
| **Indexed** | Checkbox | Non (recommandé si planifié) | Pour le workflow planifié : cocher après indexation, filtrer sur « non coché » pour ne traiter que les nouveaux. |
| **IndexedAt** | DateTime | Non | Optionnel : date/heure d’indexation (laisser vide = pas encore indexé). |
| **TableName** | SingleLineText | Non | Nom de la table (ex. `Documents`). Envoyé en `nocodb_table_name` pour retrouver le record après recherche. Si une seule table, tu peux mettre une valeur fixe dans n8n. |
| **BaseId** | SingleLineText | Non | Id de la base NocoDB. Envoyé en `nocodb_base_id` pour les liens vers l’enregistrement. |

En résumé : il te faut au minimum **l’id de l’enregistrement** et **le fichier** (ou une URL de téléchargement). Le reste améliore le suivi (Indexed / IndexedAt) et la recherche (TableName, BaseId).

### Champs envoyés à l’API (POST index)

Lors de l’appel à `POST /vectors/collections/{collection_id}/index` (en **multipart/form-data** ou form avec `file_url`) :

| Champ API | Obligatoire | Valeur / origine |
|-----------|-------------|------------------|
| `file` | Oui* | Fichier binaire (si tu ne passes pas `file_url`). |
| `file_url` | Oui* | URL du document (si tu ne passes pas `file`). |
| `document_id` | Recommandé | Id de l’enregistrement NocoDB (déduplication). Ex. `{{ $json.Id }}` ou `{{ $json.body.Id }}`. |
| `nocodb_record_id` | Recommandé | Même id que `document_id` (pour ouvrir le record après recherche). |
| `nocodb_table_name` | Optionnel | Nom de la table. Ex. `Documents` ou `{{ $json.TableName }}`. |
| `nocodb_base_id` | Optionnel | Id de la base NocoDB. Ex. `{{ $json.BaseId }}`. |

\* Il faut **soit** `file`, **soit** `file_url`.

**Pour optimi_documents (3 colonnes pièces jointes)** : utiliser `document_id` = `{recordId}_docx` / `_pdf` / `_fichier` pour unifier par fichier, et `nocodb_record_id` = id de l’enregistrement (sans suffixe) pour retrouver le bon record après recherche.

### Exemple de structure de table NocoDB

- **Id** (auto)
- **Titre** (SingleLineText) – pour affichage
- **Document** (Attachment) ou **DocumentUrl** (SingleLineText) – le fichier ou l’URL
- **Indexed** (Checkbox) – pour le planifié
- **IndexedAt** (DateTime) – optionnel
- **TableName** (SingleLineText, valeur par défaut `Documents`) – optionnel
- **BaseId** (SingleLineText) – optionnel

Si tu utilises le **webhook NocoDB**, le body envoyé à n8n doit contenir au minimum : **id** (record), **URL ou référence du fichier** (selon comment NocoDB expose les pièces jointes). Tu peux ajouter TableName, BaseId, etc. dans le body du webhook ou en valeur fixe dans n8n.

### Table optimi_documents : 3 colonnes pièces jointes

La table **optimi_documents** a **3 colonnes de type Attachment** pour trier les types de documents :

| Colonne | Rôle |
|--------|------|
| **document_docx** | Fichiers Word (.docx). |
| **document_pdf** | Fichiers PDF. |
| **fichier** | Autres types de fichiers. |

- Un même enregistrement peut avoir **un PDF et un DOCX** (sans `fichier`), ou **un seul des trois**, ou les trois.
- Il faut **indexer chaque pièce jointe non vide** : pour un record, tu peux donc avoir 1, 2 ou 3 appels à l’API d’indexation.

**Règles pour l’indexation :**

1. Pour chaque enregistrement, tester les 3 colonnes : si la colonne a une pièce jointe (URL ou fichier), faire un appel **POST index** pour ce fichier.
2. **document_id** : doit être **unique par fichier** pour éviter les doublons. Utiliser par ex. `{recordId}_docx`, `{recordId}_pdf`, `{recordId}_fichier` selon la colonne.
3. **nocodb_record_id** : garder **toujours l’id de l’enregistrement** (sans suffixe), pour que la recherche renvoie le même record NocoDB quel que soit le fichier trouvé.
4. **source_file** (ou nom envoyé à l’API) : tu peux mettre le nom du fichier ou un libellé comme `document_docx`, `document_pdf`, `fichier` pour savoir quelle colonne a été indexée.

**Exemple** : record Id = 42, avec un PDF et un DOCX remplis, `fichier` vide → 2 appels index :
- `document_id` = `42_pdf`, `nocodb_record_id` = `42`, fichier = contenu de `document_pdf`.
- `document_id` = `42_docx`, `nocodb_record_id` = `42`, fichier = contenu de `document_docx`.

En n8n : après avoir récupéré un enregistrement (Get Many ou webhook), utiliser un nœud **Code** (exemple ci-dessous) pour produire **un item par pièce jointe non vide**, puis boucler sur ces items pour appeler l’API d’indexation.

### Structure réelle renvoyée par NocoDB (Get Many)

Chaque item du Get Many ressemble à ceci (extrait) :

- **Id** (number) : id de l’enregistrement.
- **indexed** (number) : 0 = pas encore indexé, 1 = indexé (pour filtrer en planifié).
- **document_docx** : `null` ou **tableau** d’objets. Chaque objet a : `path`, `title`, `mimetype`, `size`, `id`, **`signedPath`** (chemin relatif pour le téléchargement).
- **document_pdf** : idem (tableau ou null), avec **`signedPath`**.
- **fichier** : idem (tableau ou null), avec **`signedPath`** (et parfois `thumbnails` pour les images).

Exemple d’un élément de pièce jointe :

```json
{
  "path": "download/2026/01/28/.../fichier.pdf",
  "title": "Boscard_0718-25-0001_A.pdf",
  "mimetype": "application/pdf",
  "size": 172350,
  "id": "atiof4xeebmosfx2",
  "signedPath": "dltemp/L9BRDoWNZkem4NKF/1772456400000/2026/01/28/.../fichier.pdf"
}
```

**Important** : `signedPath` est un **chemin relatif**. Pour télécharger le fichier, il faut construire l’URL complète : **URL de base NocoDB** + `signedPath` (ex. `https://ton-nocodb.com/` + `signedPath`). À configurer dans un nœud **Set** ou dans l’URL du **HTTP Request** (ex. variable d’environnement `NOCODB_BASE_URL`).

### Nœud Code (optimi_documents) : 1 record → 1 à 3 items

Entrée : un item par enregistrement (sortie du NocoDB Get Many). Sortie : un item par fichier à indexer, avec `record_id`, `document_id`, `signed_path`, `source_file`, `table_name`, `base_id`. Le nœud suivant construira `file_url` = base NocoDB + `signed_path` puis fera le GET (ou enverra `file_url` à l’API).

```javascript
const items = $input.all();
const out = [];
const TABLE_NAME = "optimi_documents";

for (const item of items) {
  const json = item.json;
  const recordId = json.Id ?? json.id;
  if (recordId == null) continue;

  // Extraire signedPath et title du premier élément d’un champ pièce jointe (tableau)
  const getAttachment = (field) => {
    if (!field || !Array.isArray(field) || field.length === 0) return null;
    const first = field[0];
    const path = first?.signedPath ?? first?.signed_path;
    const title = first?.title ?? first?.path ?? "document";
    return path ? { signedPath: path, title } : null;
  };

  const docx   = getAttachment(json.document_docx);
  const pdf    = getAttachment(json.document_pdf);
  const fichier = getAttachment(json.fichier);

  if (docx)   out.push({ json: { record_id: recordId, document_id: `${recordId}_docx`,   signed_path: docx.signedPath,  source_file: docx.title,  column: "document_docx",  table_name: TABLE_NAME, base_id: json.BaseId ?? "" } });
  if (pdf)    out.push({ json: { record_id: recordId, document_id: `${recordId}_pdf`,    signed_path: pdf.signedPath,   source_file: pdf.title,   column: "document_pdf",   table_name: TABLE_NAME, base_id: json.BaseId ?? "" } });
  if (fichier) out.push({ json: { record_id: recordId, document_id: `${recordId}_fichier`, signed_path: fichier.signedPath, source_file: fichier.title, column: "fichier", table_name: TABLE_NAME, base_id: json.BaseId ?? "" } });
}

return out;
```

**Étape suivante** : pour chaque item en sortie, construire l’URL de téléchargement puis appeler l’API.

- Dans un nœud **Set** (ou dans l’URL du HTTP Request) :  
  `file_url` = `{{ $env.NOCODB_BASE_URL || 'https://ton-nocodb.com/' }}{{ $json.signed_path }}`  
  (remplacer `https://ton-nocodb.com/` par l’URL réelle de ton NocoDB, sans slash final si `signed_path` commence déjà par un slash, ou avec un slash si `signed_path` est du type `dltemp/...`).
- Ensuite : **HTTP Request** GET sur `file_url` (Response Format: File) pour récupérer le binaire, puis **HTTP Request** POST vers l’API d’indexation avec `file`, `document_id` = `$json.document_id`, `nocodb_record_id` = `$json.record_id`, etc.  
  **Ou** envoyer directement `file_url` à l’API (paramètre `file_url`) si elle accepte l’URL NocoDB (avec auth si nécessaire).

**URL de téléchargement NocoDB** : selon ton installation, l’URL complète est soit **BASE_URL + signed_path** (ex. `https://ton-nocodb.com/` + `dltemp/xxx/...`), soit un endpoint dédié (ex. `/api/v2/storage/attachment/download?...`). Vérifier la doc NocoDB ou l’onglet réseau du navigateur lors d’un téléchargement. Si le GET nécessite un cookie ou un token, utilise les options d’auth du nœud HTTP Request (ou envoie `file_url` à l’API seulement si elle peut accéder à ton NocoDB).

### Filtrer les enregistrements « pas encore indexés » (workflow planifié)

Quand tu utilises le **Get Many**, tu peux filtrer côté n8n pour ne traiter que les lignes avec **indexed = 0** : dans un nœud **Filter**, condition `{{ $json.indexed === 0 }}` (ou `{{ $json.indexed == 0 }}`). Ainsi seuls les enregistrements non indexés sont passés au Code ci-dessus.

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

**Après le nœud Code (sortie optimi_documents)** :

| Donnée | Expression |
|--------|-------------|
| Id record (nocodb_record_id) | `{{ $json.record_id }}` |
| document_id (unique par fichier) | `{{ $json.document_id }}` |
| signedPath (chemin relatif NocoDB) | `{{ $json.signed_path }}` |
| URL complète du fichier | `{{ $env.NOCODB_BASE_URL || 'https://ton-nocodb.com/' }}{{ $json.signed_path }}` (adapter la base) |
| Nom du fichier (source_file) | `{{ $json.source_file }}` |
| Table / base | `{{ $json.table_name }}`, `{{ $json.base_id }}` |
| Filtrer non indexés (sur Get Many) | `{{ $json.indexed === 0 }}` |

**Webhook (body NocoDB)** :

| Donnée | Expression type |
|--------|------------------|
| Id record | `{{ $json.body?.Id ?? $json.body?.id }}` |
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
