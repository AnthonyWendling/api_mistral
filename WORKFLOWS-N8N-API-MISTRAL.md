# Workflows n8n – API Mistral : explication et test

Ce document explique **comment fonctionne l’enregistrement des vecteurs**, quels **workflows n8n** mettre en place, et comment **tester l’API** avec un workflow de test détaillé.

---

## 1. Comment ça marche : vecteurs et collections

### 1.1 En bref

- **Collection** = une base vectorielle (un “dossier” nommé, ex. `ma-base`). Tu peux en avoir plusieurs (une par projet, par thème, etc.).
- **Document** = un fichier (PDF, Word, Excel, PPTX, image) que tu envoies à l’API.
- **Extraction** = l’API lit le fichier et en sort du **texte brut**.
- **Chunks** = le texte est découpé en morceaux (ex. 512 caractères avec un petit chevauchement). Chaque morceau = un “chunk”.
- **Embedding (vecteur)** = chaque chunk est transformé en une liste de nombres (vecteur) par l’API Mistral Embed. Ces nombres représentent le “sens” du texte.
- **Stockage** = les vecteurs + le texte des chunks + des métadonnées (nom du fichier, URL, date) sont enregistrés dans **Chroma** (base vectorielle) dans la collection choisie.
- **Recherche** = tu envoies une **question** (ou une phrase). L’API la transforme en vecteur, compare avec tous les vecteurs de la collection, et te renvoie les **chunks les plus proches** (les plus pertinents). C’est la “recherche vectorielle”.

En résumé : **texte → chunks → vecteurs → stockés dans une collection → recherche par similarité**.

### 1.2 Les 3 façons d’alimenter une collection

| Méthode | Endpoint | Quand l’utiliser |
|--------|----------|-------------------|
| **Analyse + indexation** | `POST /analyze/document` avec `add_to_collection_id` | Tu veux à la fois une **analyse** par Mistral **et** que le document soit enregistré dans une collection. |
| **Indexation seule** | `POST /vectors/collections/{id}/index` | Tu veux **uniquement** ajouter le document à la base (sans poser de question à l’agent). Idéal pour remplir la base en masse (ex. tous les PDF d’un dossier SharePoint). |
| **Création de collection** | `POST /vectors/collections` | Une seule fois (ou quand tu veux une nouvelle base) : crée la collection par son nom. |

### 1.3 Déduplication

Si tu renvoies le **même document** (même `document_id` ou même fichier/URL), l’API ne crée **pas** de doublons : elle ne ré-indexe pas. Tu peux relancer un workflow sans remplir la base en double.

---

## 2. Workflows n8n à créer (liste)

| # | Workflow | Rôle | Déclencheur |
|---|----------|------|-------------|
| 1 | **Test API** | Vérifier que l’API répond : créer une collection, lister, (optionnel) indexer un fichier, faire une recherche. | Manuel (bouton “Test”) |
| 2 | **Créer une collection** | Créer une nouvelle base vectorielle (une fois par projet/thème). | Manuel ou au début d’un autre workflow |
| 3 | **Indexer des documents** | Envoyer des fichiers (ou URLs) à l’API pour les ajouter dans une collection (sans analyse). | Schedule, SharePoint “nouveau fichier”, ou manuel |
| 4 | **Analyser + indexer** | Analyser un document avec Mistral et, en même temps, l’enregistrer dans une collection. | Manuel, formulaire, ou après upload SharePoint |
| 5 | **Recherche (RAG)** | Poser une question → l’API renvoie les chunks pertinents → tu les envoies à Mistral (ou autre) pour une réponse finale. | Webhook, formulaire, chat |

On va détailler le **workflow 1 (test)** pour que tu puisses le recréer et tout comprendre.

---

## 3. Workflow de test – étape par étape

Objectif : **tester l’API** de bout en bout (création de collection, listage, indexation optionnelle, recherche) sans SharePoint. Tu peux tout faire avec un **déclencheur manuel** et des **HTTP Request**.

**URL de base à utiliser** : `https://apimistral-production.up.railway.app`

### Importer le workflow de test (optionnel)

Un fichier JSON de workflow est fourni dans le projet : **`n8n-workflow-test-api-mistral.json`**.

1. Dans n8n, menu **Workflows** → **Import from File** (ou glisser-déposer le fichier).
2. Sélectionne `n8n-workflow-test-api-mistral.json`.
3. Le workflow apparaît avec 4 nœuds : Déclencheur manuel → Créer collection → Lister collections → Recherche vectorielle.
4. Clique sur **Execute Workflow** (ou “Test workflow”) pour lancer le test.

Si l’import échoue (version n8n différente), recrée le workflow à la main en suivant les étapes ci-dessous.

---

### Étape 1 : Déclencheur manuel

- Ajoute un nœud **“Manual Trigger”** (Déclencheur manuel).
- Aucun paramètre. Tu lanceras le workflow en cliquant sur “Test workflow” ou “Execute Workflow”.

---

### Étape 2 : Créer une collection

- Ajoute un nœud **“HTTP Request”**.
- **Method** : `POST`
- **URL** : `https://apimistral-production.up.railway.app/vectors/collections`
- **Send Body** : Oui
- **Body Content Type** : `JSON`
- **Specify Body** : Using JSON
- **JSON** :
  ```json
  {
    "name": "test-n8n"
  }
  ```

Exécute ce nœud seul : la réponse doit être du type `{"id": "test-n8n", "name": "test-n8n"}`. L’**id** est `test-n8n` ; tu l’utiliseras pour index et search.

---

### Étape 3 : Lister les collections

- Nouveau nœud **“HTTP Request”** (branché après le précédent si tu veux enchaîner).
- **Method** : `GET`
- **URL** : `https://apimistral-production.up.railway.app/vectors/collections`

Réponse attendue : `{"collections": [{"id": "test-n8n", "name": "test-n8n"}, ...]}`. Ça confirme que la collection existe.

---

### Étape 4 (optionnel) : Indexer un document avec une URL

Si tu as une **URL publique** vers un PDF ou un fichier texte (ex. un lien direct vers un fichier) :

- Nouveau nœud **“HTTP Request”**.
- **Method** : `POST`
- **URL** : `https://apimistral-production.up.railway.app/vectors/collections/test-n8n/index`
- **Send Body** : Oui
- **Body Content Type** : `Multipart-Form`
- **Parameters** (Form Data) :
  - **Name** : `file_url` | **Type** : String | **Value** : `https://example.com/un-document.pdf`  
    (remplace par une vraie URL de fichier si tu en as une)

Exécution : la réponse contient `indexed_chunks` (nombre de morceaux enregistrés). C’est l’**enregistrement des vecteurs** : le texte a été découpé en chunks, transformé en vecteurs par Mistral Embed, et stocké dans la collection `test-n8n`.

Si tu n’as pas d’URL de fichier, tu peux **sauter cette étape** et passer à l’étape 5 en utilisant une question générique ; la recherche pourra retourner peu ou pas de résultats si la collection est vide.

---

### Étape 5 : Recherche vectorielle

- Nouveau nœud **“HTTP Request”**.
- **Method** : `POST`
- **URL** : `https://apimistral-production.up.railway.app/vectors/collections/test-n8n/search`
- **Send Body** : Oui
- **Body Content Type** : `JSON`
- **JSON** :
  ```json
  {
    "query": "De quoi parle le document ?",
    "top_k": 5
  }
  ```

Réponse : `{"results": [{ "chunk_id": "...", "text": "...", "metadata": {...}, "distance": 0.xx }, ...]}`. Chaque élément = un chunk proche de ta question. **distance** : plus c’est petit, plus c’est pertinent.

---

### Résumé du flux de test

```
[Manual Trigger] → [HTTP: POST /vectors/collections] → [HTTP: GET /vectors/collections]
                                                                    ↓
                                            [HTTP: POST .../test-n8n/index] (optionnel, file_url)
                                                                    ↓
                                            [HTTP: POST .../test-n8n/search]
```

Tu exécutes le workflow du début à la fin. À la fin, tu voit la sortie de la **recherche** : les chunks trouvés (ou une liste vide si tu n’as pas indexé de document).

---

## 4. Enchaîner les nœuds (connexions)

- Branche la **sortie** du “Manual Trigger” vers l’entrée du premier “HTTP Request” (créer collection).
- Branche la **sortie** de “Créer une collection” vers “Lister les collections”.
- Ensuite vers “Indexer” (optionnel) puis “Recherche”.
- Pour passer l’**id** de collection d’un nœud à l’autre au lieu de l’écrire en dur :  
  URL du nœud Index = `https://apimistral-production.up.railway.app/vectors/collections/{{ $json.id }}/index`  
  (si le nœud précédent a renvoyé `{"id": "test-n8n", ...}`). Même idée pour Search avec `{{ $json.id }}` si tu listes d’abord et que tu prends la première collection.

---

## 5. Tester “Analyser un document”

Pour tester **analyse + indexation** dans le même appel :

- **HTTP Request**
- **Method** : `POST`
- **URL** : `https://apimistral-production.up.railway.app/analyze/document`
- **Body Content Type** : `Multipart-Form`
- **Parameters** :
  - `file_url` (String) : une URL vers un PDF/Word/etc.
  - `add_to_collection_id` (String) : `test-n8n`
  - `document_id` (String, optionnel) : `doc-test-1`

Réponse : `analysis` (texte d’analyse Mistral) + `indexed_chunks` (nombre de chunks enregistrés dans la collection). Là encore, l’**enregistrement des vecteurs** se fait côté API : extraction → chunks → embeddings → stockage Chroma.

---

## 6. Récap : où sont enregistrés les vecteurs ?

- **Côté API** : Chroma stocke les vecteurs sur le disque (ou sur le volume Railway si tu as configuré `CHROMA_DATA_PATH=/data/chroma`). Chaque collection = un “dossier” dans Chroma.
- **Côté n8n** : n8n ne stocke pas les vecteurs. Il envoie juste les requêtes (créer collection, indexer, rechercher) et affiche les réponses. Toute la logique vecteurs/chunks/embeddings est dans l’API.

Une fois ce workflow de test OK, tu peux réutiliser les mêmes types de nœuds dans tes vrais workflows (SharePoint, RAG, etc.) en changeant juste les URLs, les noms de collections et les champs (file binaire, file_url, query, etc.) comme décrit dans **GUIDE-N8N.md**.
