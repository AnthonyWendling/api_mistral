from mistralai import Mistral

from app.config import settings

EMBED_MODEL = "mistral-embed"


def get_client() -> Mistral:
    return Mistral(api_key=settings.mistral_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    client = get_client()
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [e.embedding for e in response.data]


def embed_query(query: str) -> list[float]:
    return embed_texts([query])[0]
