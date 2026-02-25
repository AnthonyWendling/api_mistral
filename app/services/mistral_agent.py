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
