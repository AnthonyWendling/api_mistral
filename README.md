# API Mistral + recherche vectorielle

API FastAPI pour l’analyse de documents (Mistral) et la recherche vectorielle (Chroma + Mistral Embed), déployable sur Railway et utilisable depuis n8n (SharePoint, workflows).

## Fonctionnalités

- **Analyse de documents** : POST `/analyze/document` (fichier ou `file_url`) → extraction du texte (PDF, Word, Excel, PPTX, images OCR) puis analyse par Mistral. Option `add_to_collection_id` pour indexer automatiquement dans une collection.
- **Collections vectorielles** : POST `/vectors/collections`, GET `/vectors/collections`.
- **Indexation sans analyse** : POST `/vectors/collections/{id}/index` (fichier ou `file_url`) pour alimenter une base sans appel à l’agent.
- **Recherche** : POST `/vectors/collections/{id}/search` avec `{"query": "...", "top_k": 10}`.

## Installation locale

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Sur Windows, installer [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) pour l’OCR des images et ajouter son répertoire au PATH.

Copier `.env.example` vers `.env` et renseigner `MISTRAL_API_KEY`.

## Lancement

```bash
uvicorn app.main:app --reload --port 8000
```

Documentation : http://localhost:8000/docs

## Déploiement Railway

1. Créer un projet Railway et connecter le dépôt.
2. Ajouter un **volume** et le monter sur `/data` (ou un chemin de votre choix).
3. Variables d’environnement :
   - `MISTRAL_API_KEY` (obligatoire)
   - `CHROMA_DATA_PATH=/data/chroma` (pour persister Chroma sur le volume)
   - Optionnel : `LOG_LEVEL`, `MAX_FILE_SIZE_MB`, `ALLOWED_ORIGINS`
4. Déployer (build Dockerfile). Le healthcheck utilise GET `/health`.

## Intégration n8n / SharePoint

- n8n se connecte à SharePoint et récupère une URL de fichier ou le fichier.
- Envoyer à l’API soit un **fichier** (multipart), soit **file_url** (formulaire) vers POST `/analyze/document` ou POST `/vectors/collections/{id}/index`.
- L’API ne se connecte pas à SharePoint ; elle reçoit uniquement fichier ou URL.
