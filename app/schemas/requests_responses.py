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
