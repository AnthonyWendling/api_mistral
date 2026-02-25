from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.schemas.requests_responses import CollectionCreate, CollectionOut, SearchRequest, SearchResult
from app.services.extraction import extract_text
from app.services.vector_store_service import (
    add_documents,
    create_collection,
    list_collections,
    list_documents,
    search as vector_search,
)

router = APIRouter()

MAX_BYTES = settings.max_file_size_mb * 1024 * 1024


@router.post("/collections", response_model=CollectionOut)
def create_collection_route(payload: CollectionCreate):
    id_ = create_collection(payload.name)
    return CollectionOut(id=id_, name=payload.name)


@router.get("/collections")
def list_collections_route():
    return {"collections": list_collections()}


async def _get_file_from_url(file_url: str) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            r = await client.get(file_url)
            r.raise_for_status()
            if len(r.content) > MAX_BYTES:
                raise HTTPException(400, f"Fichier trop volumineux (max {settings.max_file_size_mb} Mo)")
            filename = r.url.path.split("/")[-1] or "document"
            if not filename or filename == "/":
                filename = "document"
            return r.content, filename
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"Impossible de télécharger le fichier (URL renvoie {e.response.status_code})")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Impossible d'accéder à l'URL: {str(e)}")


@router.post("/collections/{collection_id}/index")
async def index_document(
    collection_id: str,
    file: Annotated[UploadFile | None, File()] = None,
    file_url: Annotated[str | None, Form()] = None,
    document_id: Annotated[str | None, Form()] = None,
    folder_path: Annotated[str | None, Form()] = None,
    sharepoint_item_id: Annotated[str | None, Form()] = None,
    drive_id: Annotated[str | None, Form()] = None,
    site_id: Annotated[str | None, Form()] = None,
):
    if file and file.filename:
        content = await file.read()
        if len(content) > MAX_BYTES:
            raise HTTPException(400, f"Fichier trop volumineux (max {settings.max_file_size_mb} Mo)")
        filename = file.filename
    elif file_url:
        content, filename = await _get_file_from_url(file_url)
    else:
        raise HTTPException(400, "Fournir soit un fichier (multipart), soit file_url (form).")

    try:
        text = extract_text(content, filename=filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Erreur lors de l'extraction du texte: {str(e)}")

    if not text:
        return {"collection_id": collection_id, "indexed_chunks": 0, "message": "Aucun texte extrait."}

    meta = {}
    if folder_path:
        meta["folder_path"] = folder_path
    if sharepoint_item_id:
        meta["sharepoint_item_id"] = sharepoint_item_id
    if drive_id:
        meta["drive_id"] = drive_id
    if site_id:
        meta["site_id"] = site_id

    try:
        indexed = add_documents(
            collection_id,
            [text],
            document_id=document_id,
            source_file=filename,
            file_url=file_url or "",
            metadata_per_doc=meta if meta else None,
            deduplicate=True,
        )
    except Exception as e:
        err_msg = str(e)
        if "does not exist" in err_msg.lower() or "not found" in err_msg.lower():
            raise HTTPException(404, f"Collection non trouvée: {collection_id}")
        raise HTTPException(502, f"Erreur indexation (embedding ou base vectorielle): {err_msg}")

    return {"collection_id": collection_id, "indexed_chunks": indexed}


@router.get("/collections/{collection_id}/documents")
def list_documents_route(collection_id: str, limit: int = 2000):
    """Liste les documents uniques de la collection (source_file, file_url) pour savoir quoi télécharger."""
    try:
        docs = list_documents(collection_id, limit_chunks=limit)
    except Exception as e:
        err = str(e)
        if "does not exist" in err.lower() or "not found" in err.lower():
            raise HTTPException(404, f"Collection non trouvée: {collection_id}")
        raise HTTPException(502, str(e))
    return {"documents": docs, "collection_id": collection_id}


@router.post("/collections/{collection_id}/search")
def search_route(collection_id: str, payload: SearchRequest):
    try:
        results = vector_search(collection_id, payload.query, top_k=payload.top_k)
    except Exception as e:
        raise HTTPException(404, f"Collection non trouvée ou erreur: {e}")
    return {"results": [SearchResult(**r) for r in results]}
