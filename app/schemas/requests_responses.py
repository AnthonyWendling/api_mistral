from pydantic import BaseModel, Field


class AnalyzeByUrlRequest(BaseModel):
    file_url: str
    add_to_collection_id: str | None = None
    document_id: str | None = None


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1)
    parent_id: str | None = Field(None, description="ID de la collection parente pour une sous-collection (recherche vectorielle IA / Mistral)")


class CollectionOut(BaseModel):
    id: str
    name: str
    parent_id: str | None = None


class CollectionsBulkCreate(BaseModel):
    """Création en masse : liste de { name, parent_id? } ou noms seuls."""
    collections: list[CollectionCreate] = Field(..., min_length=1, max_length=500)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    include_subcollections: bool = Field(False, description="Inclure les sous-collections dans la recherche (pour LLM / Mistral)")


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    metadata: dict
    distance: float | None = None


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1)
    collection_id: str | None = Field(None, description="Si vide ou absent, recherche dans toutes les collections")
    top_k: int = Field(5, ge=1, le=20)
    system_prompt: str | None = None
    include_subcollections: bool = Field(False, description="Inclure les sous-collections (recherche IA / Mistral)")


class RAGResponse(BaseModel):
    answer: str
    sources: list[SearchResult]


# --- Transcription audio ---


class TranscriptionSegment(BaseModel):
    text: str = ""
    start: float | None = None
    end: float | None = None
    speaker_id: str | None = None


class TranscriptionUsage(BaseModel):
    prompt_audio_seconds: float | None = None
    prompt_tokens: int | None = None
    total_tokens: int | None = None
    completion_tokens: int | None = None


class TranscriptionResponse(BaseModel):
    text: str
    language: str | None = None
    model: str | None = None
    segments: list[TranscriptionSegment] = []
    usage: dict | None = None


class MeetingAnalysisResponse(BaseModel):
    transcript: TranscriptionResponse | str
    analysis: str
