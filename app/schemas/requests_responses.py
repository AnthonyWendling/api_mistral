from pydantic import BaseModel, Field


class AnalyzeByUrlRequest(BaseModel):
    file_url: str
    add_to_collection_id: str | None = None
    document_id: str | None = None


class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1)


class CollectionOut(BaseModel):
    id: str
    name: str


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=100)


class SearchResult(BaseModel):
    chunk_id: str
    text: str
    metadata: dict
    distance: float | None = None


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1)
    collection_id: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    system_prompt: str | None = None


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
