# Indexation des documents NocoDB dans l’API (n8n)

Ce guide décrit comment **déclencher l’indexation** quand un document est enregistré dans NocoDB, et comment choisir entre **déclenchement à l’enregistrement** (recommandé) et **mise à jour planifiée** (tous les jours).

---

## Comparaison des approches

| Approche | Avantages | Inconvénients |
|----------|-----------|----------------|
| **Webhook NocoDB → n8n** (à l’enregistrement) | Indexation quasi immédiate, pas de re-scan inutile, simple à maintenir | Dépend de la config webhook NocoDB |
| **Planifié (ex. tous les jours)** | Pas besoin de webhook, peut rattraper des oublis | Délai (jusqu’à 24 h), il faut identifier les « nouveaux » ou « modifiés » (date, flag, etc.) |
| **Hybride** | Webhook pour le temps réel + planifié en secours | Deux workflows à maintenir |

**Recommandation** : privilégier le **webhook NocoDB** qui appelle un workflow n8n à chaque création (et éventuellement mise à jour) d’enregistrement. Si NocoDB ne peut pas appeler n8n, ou en complément, utiliser un workflow **planifié** (ex. une fois par jour) qui détecte les nouveaux enregistrements et les indexe.

---

## 1. Approche recommandée : webhook NocoDB (à l’enregistrement)

Dès qu’un enregistrement est créé (ou mis à jour) dans la table qui contient les documents, NocoDB envoie une requête HTTP vers une URL de ton choix. Tu pointes cette URL vers un **webhook n8n** qui : récupère le fichier (pièce jointe ou URL), appelle l’API d’indexation, et stocke les métadonnées NocoDB pour pouvoir retrouver le bon enregistrement après une recherche.

### 1.1 Configurer le webhook dans NocoDB

1. Ouvre la **table** qui contient les documents (et éventuellement un champ pièce jointe / fichier ou une URL).
2. Va dans **Automation** (ou **Webhooks**) pour cette table.
3. Crée un **webhook** :
   - **Trigger** : **After Insert** (obligatoire pour les nouveaux enregistrements). Optionnel : **After Update** si tu veux ré-indexer quand un document est modifié.
   - **Action** : envoyer une requête HTTP (POST) vers l’URL de ton **webhook n8n** (voir ci-dessous).
   - **Body** : tu peux envoyer tout l’enregistrement (ou les champs utiles) en JSON, par ex. `{{ record }}` ou les champs nécessaires (id, champ fichier/URL, nom de table, base id, etc.).

Référence NocoDB : [Webhooks](https://docs.nocodb.com/developer-resources/webhooks/).

### 1.2 Workflow n8n : webhook → indexation

1. **Déclencheur** : nœud **Webhook** (POST), URL exposée par n8n (ex. `https://ton-n8n.com/webhook/nocodb-index`).

2. **Entrée** : le body envoyé par NocoDB contient au minimum l’**id** de l’enregistrement et de quoi récupérer le **fichier** :
   - soit une **URL** de téléchargement (champ type URL ou pièce jointe avec lien),
   - soit un **chemin / identifiant** pour récupérer le fichier via l’API NocoDB dans un nœud suivant.

3. **Récupérer le fichier** :
   - Si NocoDB envoie une **URL** publique ou signée du fichier : utilise **HTTP Request** (GET sur cette URL) pour récupérer le binaire, ou passe directement cette URL à l’API (paramètre `file_url`).
   - Si le fichier est dans NocoDB (attachment) : utilise le nœud **NocoDB** (opération adaptée pour récupérer la pièce jointe) ou l’**API NocoDB** (HTTP Request) pour télécharger le fichier, puis envoie le binaire à l’API.

4. **Appeler l’API d’indexation** :
   - **HTTP Request** :
     - Method : **POST**
     - URL : `https://apimistral-production.up.railway.app/vectors/collections/TA_COLLECTION_ID/index`
     - Body : **Multipart Form** (si tu envoies un fichier binaire) ou **form-data** avec `file_url` si tu as une URL.
   - Champs à envoyer :
     - `file` (binaire) **ou** `file_url` (URL du document)
     - `document_id` : **id de l’enregistrement NocoDB** (ex. `{{ $json.Id }}` ou le champ id envoyé par le webhook) pour déduplication
     - `nocodb_record_id` : même id (pour retrouver l’enregistrement après recherche)
     - `nocodb_table_name` : nom de la table (ex. `{{ $json.TableName }}` ou valeur fixe)
     - `nocodb_base_id` : id de la base NocoDB (optionnel, si tu veux le garder pour les liens)

Tu peux utiliser une **seule collection** (ex. `nocodb-documents`) ou plusieurs (par table ou par type), en mettant `collection_id` dans l’URL.

5. **Gestion d’erreurs** : active **Continue On Fail** sur l’appel HTTP d’indexation pour ne pas faire échouer tout le workflow si un fichier est invalide ou non supporté.

### 1.3 Exemple de payload NocoDB → n8n

NocoDB peut envoyer par exemple (à adapter selon ta config webhook) :

```json
{
  "id": 42,
  "Title": "Mon document",
  "Attachment": "https://..../attachment-url",
  "TableName": "Documents",
  "BaseId": "p_xxx"
}
```

Dans n8n, tu utilises `$json.id` comme `document_id` et `nocodb_record_id`, `$json.Attachment` comme `file_url` (ou tu télécharges le binaire), et `$json.TableName` / `$json.BaseId` pour les métadonnées.

---

## 2. Approche alternative : mise à jour planifiée (ex. tous les jours)

Si tu ne peux pas utiliser le webhook NocoDB, ou en complément, tu peux lancer un workflow n8n **planifié** (ex. tous les jours à 6 h) qui :

1. **Liste les enregistrements** de la table documents (nœud **NocoDB** – Get Many, ou HTTP Request vers l’API NocoDB).
2. **Filtre** les nouveaux ou modifiés :
   - soit avec un champ **date** (ex. `CreatedAt` / `UpdatedAt`) et ne garder que ceux modifiés depuis la dernière exécution (tu stockes la dernière date en variable ou dans un store),
   - soit avec un champ **déjà indexé** (ex. `IndexedAt` ou `Indexed` booléen) et ne traiter que ceux où `IndexedAt` est vide ou `Indexed` = false.
3. Pour **chaque** enregistrement à indexer :
   - Récupérer le fichier (URL ou pièce jointe via NocoDB).
   - **POST** vers `.../vectors/collections/TA_COLLECTION_ID/index` avec `file` ou `file_url`, `document_id` = id record, `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`.
   - Optionnel : mettre à jour l’enregistrement NocoDB (champ `IndexedAt` = maintenant ou `Indexed` = true) pour ne pas le ré-indexer au prochain run.

Inconvénient : tout le contenu nouveau n’est indexé qu’après le prochain run (délai jusqu’à 24 h si planifié 1×/jour). Avantage : pas besoin de webhook, et tu peux rattraper des enregistrements qui auraient été manqués par le webhook.

---

## 3. Métadonnées NocoDB côté API

L’API accepte désormais, en plus des champs SharePoint, les champs suivants à l’indexation (en **form** multipart) :

| Champ | Description |
|-------|-------------|
| `nocodb_record_id` | Id de l’enregistrement (pour ouvrir le bon record après recherche). |
| `nocodb_table_name` | Nom de la table (pour construire un lien ou un filtre). |
| `nocodb_base_id` | Id de la base NocoDB (optionnel). |

Ils sont stockés avec les vecteurs et **renvoyés** dans la réponse de **search-documents** (et dans la liste des documents de la collection). Ainsi, après une recherche, ton flow n8n peut utiliser `nocodb_record_id` (et table/base) pour ouvrir ou afficher le bon enregistrement dans NocoDB.

---

## 4. Recherche puis ouverture du record NocoDB

Une fois les documents indexés (avec `nocodb_record_id`, etc.) :

1. **Recherche** : POST `/webhooks/search-documents` avec `query` et `collection_id`.
2. La réponse contient **`documents`** : chaque élément peut contenir `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`.
3. Dans n8n (ou ton app), tu peux construire l’**URL NocoDB** vers l’enregistrement (ex. `https://ton-nocodb.com/base/.../table/.../record/{{ nocodb_record_id }}`) ou appeler l’API NocoDB pour récupérer le détail du record.

---

## 5. Résumé

- **Mieux** : **webhook NocoDB** (After Insert, éventuellement After Update) qui appelle un **webhook n8n** → récupération du fichier (URL ou binaire) → **POST** `.../vectors/collections/{id}/index` avec `document_id`, `nocodb_record_id`, `nocodb_table_name`, `nocodb_base_id`. Indexation à l’enregistrement.
- **Alternative / secours** : workflow **planifié** (ex. 1×/jour) qui liste les enregistrements nouveaux ou non indexés, récupère le fichier, appelle le même endpoint d’indexation, et optionnellement marque l’enregistrement comme indexé.
- Les champs **nocodb_*** sont disponibles dans les réponses de recherche pour retrouver et ouvrir le bon enregistrement NocoDB après une recherche sémantique.
