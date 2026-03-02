# n8n : indexation NocoDB → API Mistral (guide pas à pas)

Guide **n8n** pour déclencher l’indexation des documents NocoDB dans les collections de l’API (webhook à l’enregistrement ou workflow planifié).

---

## Prérequis

- **n8n** avec accès à ton instance (self-hosted ou cloud).
- **Credential NocoDB** configurée dans n8n (URL de l’API + token).
- **API Mistral** déployée (ex. `https://apimistral-production.up.railway.app`).
- Les **collections** sont créées **par affaire** (voir section ci-dessous) ; pas besoin de créer une seule collection globale à l’avance.

---

## Collections par affaire (à faire avant d’indexer)

Pour que la recherche soit utile par affaire, il faut **une collection par affaire** (et non une seule collection pour tous les documents). Chaque document est indexé dans la collection qui correspond à son `affaire_id` (ou `numero_affaire`).

### Convention de nom

- **Nom de collection** : `nocodb-affaire-{affaire_id}` (ex. `nocodb-affaire-88`) ou `Affaire {numero_complet}` (ex. `Affaire 8888-24-0001`).
- L’API transforme le nom en **id** (slug : minuscules, chiffres, tirets). Ex. `nocodb-affaire-88` → id `nocodb-affaire-88` ; `Affaire 8888-24-0001` → id `affaire-8888-24-0001`.

### Créer la collection avant d’indexer

1. **Endpoint** : `POST /vectors/collections`  
   Body JSON : `{ "name": "nocodb-affaire-{{ affaire_id }}" }` (avec la valeur réelle de l’affaire, ex. `88`).
2. L’API utilise **get_or_create** : si la collection existe déjà, elle est réutilisée ; sinon elle est créée. Tu peux donc appeler ce POST à chaque indexation sans risque de doublon.
3. **Dans n8n** : avant d’appeler l’indexation pour un document, appelle une fois `POST .../vectors/collections` avec le nom de la collection de l’affaire de ce document. Puis appelle `POST .../vectors/collections/{collection_id}/index` avec le même `collection_id` (ex. `nocodb-affaire-88`).

### Ordre dans le workflow

1. Récupérer les documents (Get Many, puis Code pour 1 record → 1 à 3 items).
2. **Pour chaque item** :  
   - **Créer la collection de l’affaire** (si pas encore faite) :  
     `POST https://.../vectors/collections`  
     Body : `{ "name": "nocodb-affaire-{{ $json.affaire_id }}" }`  
     (utilise `$json.affaire_id` qui sort du nœud Code.)
   - **Ensuite** : indexer le document dans cette collection :  
     `POST https://.../vectors/collections/nocodb-affaire-{{ $json.affaire_id }}/index`  
     avec `file_url`, `document_id`, `nocodb_record_id`, `affaire_id`, `numero_affaire`, etc.

Si `affaire_id` est vide pour un enregistrement, tu peux utiliser une collection par défaut (ex. `nocodb-sans-affaire`) en créant cette collection une fois et en utilisant son id pour ces documents.

---

## Collections par catégorie (contraintes, univers, secteur, domaine, lots)

En plus des collections **par affaire**, tu peux créer des collections **par catégorie** (famille de contrainte, univers, secteur d’activité, domaine d’application, lots). L’**IA analyse le document** pour décider dans quelles catégories le ranger ; chaque document est alors indexé dans la **collection de l’affaire** et dans **chaque collection catégorie** qui s’applique. Ainsi, on ne crée une collection que si elle n’existe pas encore, et on enregistre le document dans les bonnes collections.

### Vérifier si une collection existe avant de la créer

- **GET** `https://.../vectors/collections` → liste des collections existantes (`id`, `name`).
- **POST** `https://.../vectors/collections/ensure` avec body `{ "name": "Contrainte sécurité" }` → crée la collection **seulement si elle n’existe pas** (l’id sera dérivé du nom, ex. `contrainte-securite`). Réponse : `{ "id": "contrainte-securite", "created": true }` ou `"created": false` si elle existait déjà.
- Utiliser **ensure** avant d’indexer pour chaque collection (affaire + catégories) sans créer de doublon.

### Classifier le document avec l’IA

- **POST** `https://.../webhooks/classify-document`  
  Body : `{ "text": "..." }` (texte brut) **ou** `{ "file_url": "https://..." }` (l’API télécharge le fichier, extrait le texte, puis classe).  
  Réponse : `famille_contraintes`, `univers`, `secteur_activite`, `domaine_application`, `lots`, et **`collection_ids`** (liste d’ids de collections dans lesquelles indexer le document, ex. `["contrainte-securite", "univers-materiel", "lot-electricite-automatisme"]`).

### Taxonomie (listes officielles)

Les ids de collection sont dérivés du libellé (minuscules, tirets). Ex. « Contrainte sécurité » → `contrainte-securite`, « Electricité / Automatisme » → `lot-electricite-automatisme`.

**Famille de contrainte** (préfixe `contrainte-`) :  
Contrainte d'implantation, Contrainte d'hygiène, Contrainte de production, Contrainte de qualité, Contrainte environnementale, Contrainte ergonomique, Contrainte financière, Contrainte maintenance, Contrainte organisationnelle, Contrainte planning, Contrainte produit, Contrainte projet, Contrainte réglementaire, Contrainte sécurité, Contrainte technique, Contrainte de confidentialité, Contrainte d'accessibilité, Contrainte logistique, Contrainte de performance, Contrainte d'intégration.

**Univers** (préfixe `univers-`) :  
Milieu, Matière, Méthode, Main d'œuvre, Matériel, Sécurité, Qualité.

**Secteur d'activité** (préfixe `secteur-`) :  
Générique, Agroalimentaire, Cosmétique, Mécanique, Pharmaceutique, Chimie, Papeterie, Menuiserie, Packaging.

**Domaine d'application** (préfixe `domaine-`) :  
Process, Logistique, Utilités, Infrastructure, Autres, Étude de flux, Nettoyage, PID, Étude de sol, Sécurité, ATEX, Normes, Chantier, DAO / CAO, Conditionnement.

**Lots** (préfixe `lot-`) :  
Electricité / Automatisme, Machine / Equipement, Convoyeur, Utilité : Air comprimé, Utilité : Équipement thermique, Second œuvre : Bâtiment interne, VRD (voirie Réseau Divers), Construction métallique, Transfert équipements, Equipements frigorifiques et Isolation / calorifugeage, Utilité : Isolation / calorifugeage, Salle blanche, Etudes / ingénierie / calculs, Génie civil / gros œuvre, Utilité : Hydraulique et pneumatique, Utilité : Réseau / Informatique, Manutention / levage, Nettoyage industriel / NEP, Rack / stockage / Palettier / Echafaudage, Utilité : Incendie, Utilité : Traitement de l'air, Tuyauteur - Chaudronnier, Serrurerie - Plateforme, VSM (Value Stream Mapping), AGV.

La liste complète des **specs** (id + name + type) est exposée par l’API : **GET** `https://.../vectors/collections/category-specs` → `{ "specs": [ { "id": "contrainte-securite", "name": "Contrainte sécurité", "type": "famille_contrainte" }, ... ] }`.

### Workflow n8n 1 : Créer les collections catégories (une fois ou périodiquement)

Objectif : créer **uniquement les collections qui n’existent pas encore** (par contrainte, univers, secteur, domaine, lot).

1. **Schedule** ou **manuel**.
2. **HTTP Request** – GET `https://.../vectors/collections` → récupérer la liste des collections existantes. Sortie : `collections` (tableau avec `id`).
3. **HTTP Request** – GET `https://.../vectors/collections/category-specs` → récupérer `specs` (toutes les collections catégorie à avoir).
4. **Code** : pour chaque `spec` dans `specs`, si `spec.id` **n’est pas** dans les `id` des collections existantes, produire un item `{ "id": spec.id, "name": spec.name }`. Sinon ne pas produire d’item (pour ne pas recréer).
5. **Loop** sur les items en sortie du Code.
6. **HTTP Request** – POST `https://.../vectors/collections/ensure`  
   Body JSON : `{ "name": "{{ $json.name }}" }` (ou `{{ $json.id }}` car l’id slugué est identique).  
   Ainsi on ne crée que les collections manquantes.

### Workflow n8n 2 : Indexer un document avec classification IA (et collections par affaire)

Objectif : pour chaque document NocoDB, **analyser le document avec l’IA**, s’assurer que les collections (affaire + catégories) existent, puis **indexer le document dans la collection affaire et dans chaque collection catégorie** retournée par l’IA.

1. Récupérer les documents (NocoDB Get Many, filtre `indexed === 0`, puis **Code** optimi_documents → 1 record → 1 à 3 items avec `file_url`, `record_id`, `document_id`, `affaire_id`, `numero_affaire`, etc.).
2. Pour chaque item (chaque fichier à indexer) :
   - **Option A** : envoyer l’URL du fichier à l’IA pour classification.  
     **HTTP Request** – POST `https://.../webhooks/classify-document`  
     Body JSON : `{ "file_url": "{{ $env.NOCODB_BASE_URL }}{{ $json.signed_path }}" }` (ou le champ `file_url` déjà construit).  
     Réponse : `collection_ids` (liste d’ids de collections catégorie) + les libellés (famille_contraintes, univers, etc.).
   - **Option B** : si tu as déjà le texte (ex. extrait ailleurs), Body : `{ "text": "{{ $json.extracted_text }}" }`.
3. **Ensure collection affaire** :  
   **HTTP Request** – POST `https://.../vectors/collections/ensure`  
   Body : `{ "name": "nocodb-affaire-{{ $('Code').item.json.affaire_id }}" }` (adapter le nom du nœud qui porte `affaire_id`).
4. **Ensure collections catégories** : pour chaque `collection_id` dans `collection_ids` de la réponse classify, appeler **POST** `https://.../vectors/collections/ensure` avec `{ "name": "{{ $json.collection_id }}" }`. En n8n : un nœud **Code** qui prend l’item courant + la réponse classify et produit **un item par collection_id** ; puis boucle sur ces items et **HTTP Request** POST ensure pour chaque. (Ou en une seule boucle : ensure affaire, puis pour chaque id dans `collection_ids` ensure + index.)
5. **Indexer dans la collection affaire** :  
   **HTTP Request** – POST `https://.../vectors/collections/nocodb-affaire-{{ $('Code').item.json.affaire_id }}/index`  
   Body form : `file_url`, `document_id`, `nocodb_record_id`, `affaire_id`, `numero_affaire`, etc.
6. **Indexer dans chaque collection catégorie** : pour chaque `collection_id` dans `collection_ids`,  
   **HTTP Request** – POST `https://.../vectors/collections/{{ $json.collection_id }}/index`  
   avec les mêmes champs (file_url, document_id, nocodb_record_id, affaire_id, numero_affaire).  
   En n8n : après le Code qui éclate en un item par collection_id, faire une boucle : ensure puis index pour cet id.
7. (Optionnel) Marquer le record NocoDB comme indexé (**NocoDB Update**).

Résumé : **ne créer une collection que si elle n’existe pas** (ensure) ; **enregistrer le document dans la bonne collection affaire et dans les collections catégories** déterminées par l’IA.

### Trouver le document adéquat (recherche)

- **Par affaire** : `POST /webhooks/search-documents` avec `collection_id: "nocodb-affaire-88"` et ta `query` → les documents indexés dans cette affaire.
- **Par catégorie** : même appel avec `collection_id: "contrainte-securite"` (ou `univers-materiel`, `lot-electricite-automatisme`, etc.) → les documents que l’IA a classés dans cette catégorie.
- La réponse contient `documents` avec `nocodb_record_id`, `file_url`, `affaire_id`, `numero_affaire`, etc., pour ouvrir ou télécharger le bon document.

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
| `affaire_id` | Optionnel | Id de l’affaire (ex. `{{ $json.affaire_id }}` ou `{{ $json.ouptimi_affaires_id }}`). Utile pour filtrer ou afficher les résultats par affaire. |
| `numero_affaire` | Optionnel | Numéro d’affaire (ex. `{{ $json.numero_complet }}`). Aide à identifier l’affaire dans les résultats de recherche. |

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

  const affaireId = String(json.ouptimi_affaires_id ?? json.affaire_id ?? "");
  const numeroAffaire = json.numero_complet ?? "";

  if (docx)   out.push({ json: { record_id: recordId, document_id: `${recordId}_docx`,   signed_path: docx.signedPath,  source_file: docx.title,  column: "document_docx",  table_name: TABLE_NAME, base_id: json.BaseId ?? "", affaire_id: affaireId, numero_affaire: numeroAffaire } });
  if (pdf)    out.push({ json: { record_id: recordId, document_id: `${recordId}_pdf`,    signed_path: pdf.signedPath,   source_file: pdf.title,   column: "document_pdf",   table_name: TABLE_NAME, base_id: json.BaseId ?? "", affaire_id: affaireId, numero_affaire: numeroAffaire } });
  if (fichier) out.push({ json: { record_id: recordId, document_id: `${recordId}_fichier`, signed_path: fichier.signedPath, source_file: fichier.title, column: "fichier", table_name: TABLE_NAME, base_id: json.BaseId ?? "", affaire_id: affaireId, numero_affaire: numeroAffaire } });
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
- `affaire_id` → `{{ $json.body?.ouptimi_affaires_id ?? $json.body?.affaire_id ?? '' }}`
- `numero_affaire` → `{{ $json.body?.numero_complet ?? $json.body?.numero_affaire ?? '' }}`
- `collection_id` → **par affaire** : `nocodb-affaire-{{ $json.body?.ouptimi_affaires_id ?? $json.body?.affaire_id ?? 'sans-affaire' }}` (créer la collection à l’étape 3b avant d’indexer).

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

### Étape 3b : Créer la collection de l’affaire (si tu utilises une collection par affaire)

- Nœud **HTTP Request** :
  - **Method** : POST.
  - **URL** : `https://apimistral-production.up.railway.app/vectors/collections`
  - **Body** (JSON) : `{ "name": "{{ $('Set').first().json.collection_id }}" }`  
    (le `collection_id` du Set est déjà du type `nocodb-affaire-88` ; l’API crée ou réutilise la collection.)

### Étape 4 : Appeler l’API d’indexation

Ajouter un nœud **HTTP Request**.

- **Method** : POST.
- **URL** :  
  `https://apimistral-production.up.railway.app/vectors/collections/{{ $('Set').first().json.collection_id ?? 'nocodb-sans-affaire' }}/index`  
  (remplace `Set` par le nom de ton nœud ; `collection_id` doit être cohérent avec le nom créé à l’étape 3b, ex. `nocodb-affaire-88`).

- **Send Body** : Oui.
- **Body Content Type** : **Multipart-Form** (si tu envoies un fichier binaire) **ou** **Form-Data** (si tu envoies seulement `file_url`).

**Si tu as un fichier binaire (Cas A ou B)** :

| Name               | Type         | Value / Expression |
|--------------------|--------------|--------------------|
| `file`             | Binary Data  | Binary Property = `data` (ou le nom de la propriété binaire du nœud précédent) |
| `document_id`      | String       | `{{ $('Set').first().json.record_id ?? $json.body?.Id ?? $json.body?.id }}` |
| `nocodb_record_id` | String       | même expression que `document_id` |
| `nocodb_table_name`| String       | `{{ $('Set').first().json.table_name ?? 'Documents' }}` |
| `nocodb_base_id`   | String       | `{{ $('Set').first().json.base_id ?? '' }}` |
| `affaire_id`       | String       | `{{ $('Set').first().json.affaire_id ?? $json.body?.affaire_id ?? '' }}` |
| `numero_affaire`   | String       | `{{ $('Set').first().json.numero_affaire ?? $json.body?.numero_affaire ?? '' }}` |

**Si tu envoies seulement une URL (Cas C)** :

| Name               | Type  | Value / Expression |
|--------------------|-------|--------------------|
| `file_url`         | String| `{{ $json.file_url ?? $json.body?.Attachment ?? $json.body?.FileUrl }}` |
| `document_id`      | String| `{{ $json.body?.Id ?? $json.body?.id }}` |
| `nocodb_record_id` | String| même que `document_id` |
| `nocodb_table_name`| String| `{{ $json.body?.TableName ?? 'Documents' }}` |
| `nocodb_base_id`   | String| `{{ $json.body?.BaseId ?? '' }}` |
| `affaire_id`       | String| `{{ $json.body?.affaire_id ?? '' }}` |
| `numero_affaire`   | String| `{{ $json.body?.numero_affaire ?? '' }}` |

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

1. Ajouter un nœud **"Loop Over Items"** (ou utiliser le flux par défaut de n8n si chaque item correspond déjà à un document).
   - Ce nœud va itérer sur tous les enregistrements récupérés à l’étape 2/3.

2. À l’intérieur de la boucle, pour chaque item :
   - Ajouter un nœud **"Set"** pour extraire et nommer explicitement les champs nécessaires :
     - **Cas avec une structure complexe comme l’API fournie ci-dessus** (exemple pour `optimi_documents` avec un champ `fichier` tableau) :
       -  Dans le nœud **Set** (après extraction avec un nœud Function/Code si besoin) :
         - `file_url` = `{{ $env.NOCODB_BASE_URL || 'https://ton-nocodb.com/' }}{{ $json.fichier[0].signedPath }}`
         - `record_id` = `{{ $json.Id || $json.id }}`
         - `document_id` = `{{ $json.Id || $json.id }}`
         - `table_name` = `optimi_documents`
         - `base_id` = `{{ $json.BaseId ?? '' }}`
         - `affaire_id` = `{{ $json.ouptimi_affaires_id ?? $json.affaire_id ?? '' }}`
         - `numero_affaire` = `{{ $json.numero_complet ?? '' }}`
         - (Tu peux extraire le nom de fichier avec `{{ $json.fichier[0].title }}` si besoin dans les métadonnées.)
     - **Cas d’une table avec seulement une colonne Attachment/URL** :
         - `url_fichier` = `{{ $json.Attachment ?? $json.FileUrl }}`
         - `record_id` = `{{ $json.Id ?? $json.id }}`
         - `table_name` = `{{ $json.TableName ?? 'Documents' }}`
         - `base_id` = `{{ $json.BaseId ?? '' }}`
     
   - Ensuite, ajouter un nœud **"IF"** pour tester si tu obtiens une vraie URL dans `file_url` ou `url_fichier` :
     - Condition : `{{ $json.file_url || $json.url_fichier }}` is not empty

     - **Dans le cas OUI (`file_url` ou `url_fichier` existe et n’est pas vide) :**
       - Ajouter un nœud **"HTTP Request"** avec :
         - **Method** : GET
         - **URL** : `{{ $json.file_url || $json.url_fichier }}`
         - **Response Format** : File (pour télécharger le binaire du document)
       - La sortie contiendra la donnée binaire à utiliser comme `file` dans l’étape d’indexation.

     - **Sinon (non disponible ou non exploitable)** :
       - Garder la valeur `url_fichier` pour envoi direct sous forme de champ `file_url` à l’API d’indexation (à l’étape suivante).

   - Tu peux également utiliser un nœud **"Switch"** si tu souhaites gérer différents types/champs de pièces jointes selon la structure de tes données NocoDB (ex : différencier `Attachment`, `FileUrl`, autre champ…).

Résumé :  
- Pour chaque enregistrement, le flux va soit : télécharger le fichier (si possible) pour l’envoyer en binaire, soit préparer le champ `file_url` pour l’API d’indexation.

### Étape 5a : Créer la collection de l’affaire (avant d’indexer)

- Nœud **HTTP Request** :
  - **Method** : POST.
  - **URL** : `https://apimistral-production.up.railway.app/vectors/collections` (adapter l’URL de ton API).
  - **Body** (JSON) : `{ "name": "nocodb-affaire-{{ $json.affaire_id }}" }`  
    (si `affaire_id` peut être vide, utiliser un nom par défaut, ex. `nocodb-sans-affaire`, avec une condition **IF** sur `$json.affaire_id`).
- Pas besoin de récupérer la réponse pour la suite : l’id de la collection sera `nocodb-affaire-{{ $json.affaire_id }}` (slug du nom).

### Étape 5b : Appeler l’API d’indexation (dans la collection de l’affaire)

- Nœud **HTTP Request** (juste après la création de collection) :
  - **URL** : `https://apimistral-production.up.railway.app/vectors/collections/nocodb-affaire-{{ $json.affaire_id }}/index`  
    (même convention que le nom de collection : id = `nocodb-affaire-88` pour affaire_id 88).
  - Body Multipart ou Form selon que tu envoies `file` (binaire) ou `file_url`.
  - Champs : `document_id`, `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`, `affaire_id`, `numero_affaire` (ex. `$json.record_id`, `$json.document_id`, `$json.affaire_id`, `$json.numero_affaire` après le Code).
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
| Id affaire (affaire_id) | `{{ $json.affaire_id }}` |
| Numéro d’affaire (numero_affaire) | `{{ $json.numero_affaire }}` |
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
  Body (multipart) : `file` ou `file_url`, `document_id`, `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`, `affaire_id`, `numero_affaire`.
- **Recherche** : `POST /webhooks/search-documents`  
  Body JSON : `{ "query": "...", "collection_id": "...", "top_k": 10 }`  
  Réponse : `results` (chunks) + `documents` (avec `nocodb_record_id`, etc.).

Voir **GUIDE-NOCODB-INDEXATION.md** pour la vue d’ensemble et **DOCUMENTATION.md** pour tous les endpoints.
