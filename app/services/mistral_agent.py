from mistralai import Mistral

from app.config import settings

DEFAULT_SYSTEM = (
    "Tu es un assistant qui analyse des documents. Tu fournis une analyse claire, structurée et utile du contenu fourni."
)
MAX_TEXT_LENGTH = 128_000


def get_client() -> Mistral:
    return Mistral(api_key=settings.mistral_api_key)


def analyze_document(text: str, system_prompt: str | None = None) -> str:
    if not text.strip():
        return "Aucun texte extrait du document."
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n\n[... texte tronqué ...]"
    client = get_client()
    response = client.chat.complete(
        model="open-mistral-7b",
        messages=[
            {"role": "system", "content": system_prompt or DEFAULT_SYSTEM},
            {"role": "user", "content": f"Analyse le document suivant:\n\n{text}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def analyze_with_prompt(text: str, prompt: str, system_prompt: str | None = None) -> str:
    """Analyse un document avec un prompt utilisateur personnalisé."""
    if not text.strip():
        return "Aucun texte extrait du document."
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "\n\n[... texte tronqué ...]"
    client = get_client()
    system = system_prompt or "Tu es un assistant qui répond de façon précise en t'appuyant sur le document fourni."
    user_content = f"{prompt}\n\n---\nDocument :\n{text}"
    response = client.chat.complete(
        model="open-mistral-7b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def rag_answer(context: str, query: str, system_prompt: str | None = None) -> str:
    """Répond à une question en s'appuyant sur un contexte (chunks issus de la recherche vectorielle)."""
    if not context.strip():
        return "Aucun contexte fourni pour répondre."
    client = get_client()
    system = system_prompt or (
        "Tu réponds uniquement à partir du contexte fourni. Si le contexte ne permet pas de répondre, dis-le. Réponse concise et fiable."
    )
    user_content = f"Contexte :\n{context}\n\nQuestion : {query}"
    if len(user_content) > MAX_TEXT_LENGTH:
        user_content = user_content[:MAX_TEXT_LENGTH] + "\n\n[... tronqué ...]"
    response = client.chat.complete(
        model="open-mistral-7b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def suggest_collections_from_folders(folders_text: str) -> str:
    """
    Propose les meilleures collections à créer à partir de la structure des dossiers SharePoint.
    """
    if not folders_text.strip():
        return "Aucun dossier fourni."
    client = get_client()
    system = """Tu es un expert en organisation documentaire. On te donne la liste des dossiers d'un SharePoint.
Ta tâche : proposer les MEILLEURES collections (bases vectorielles) à créer dans une API de recherche sémantique, pour que l'IA apprenne de façon claire et retrouve facilement les bons documents.

Règles :
- Chaque collection = un thème ou un type d'affaire (ex: "contrats", "affaires-commerciales", "comptabilite").
- Utilise des noms de collection en minuscules, sans espaces (tirets autorisés), courts et parlants.
- Regroupe les dossiers qui vont ensemble dans la même collection.
- Réponds en JSON valide uniquement, sans texte avant ou après, sous cette forme exacte :
{
  "collections": [
    {
      "name": "nom-collection",
      "description": "Courte description du contenu et de l'usage.",
      "folder_paths": ["/chemin/dossier1", "/chemin/dossier2"]
    }
  ]
}
Si tu n'as qu'un seul dossier logique, une seule collection. Si la structure est très variée, propose plusieurs collections thématiques."""
    user = f"Liste des dossiers SharePoint (path | name) :\n{folders_text}"
    if len(user) > MAX_TEXT_LENGTH:
        user = user[:MAX_TEXT_LENGTH] + "\n\n[... tronqué ...]"
    response = client.chat.complete(
        model="open-mistral-7b",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (response.choices[0].message.content or "").strip()
