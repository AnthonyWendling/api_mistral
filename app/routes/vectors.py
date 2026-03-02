from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.schemas.requests_responses import CollectionCreate, CollectionOut, CollectionsBulkCreate, SearchRequest, SearchResult
from app.services.extraction import extract_text
from app.services.vector_store_service import (
    add_documents,
    create_collection,
    delete_collection,
    delete_document,
    list_collections,
    list_documents,
    search as vector_search,
)
from app.services.document_classification import get_all_category_collection_specs
from app.services.sources_service import (
    create_source,
    delete_source,
    get_source,
    list_sources,
    update_source,
    sync_nocodb_source,
)
from app.schemas.sources import SourceCreate, SourceUpdate, SourceOut

router = APIRouter()

MAX_BYTES = settings.max_file_size_mb * 1024 * 1024


@router.post("/collections", response_model=CollectionOut)
def create_collection_route(payload: CollectionCreate):
    id_ = create_collection(payload.name, parent_id=payload.parent_id)
    parent_id = payload.parent_id
    return CollectionOut(id=id_, name=payload.name, parent_id=parent_id)


@router.get("/collections")
def list_collections_route(tree: bool = False):
    """
    Liste les collections (et sous-collections). Pour l'IA / recherche vectorielle Mistral.
    tree=true : retourne un arbre { "collections": [ { "id", "name", "parent_id", "children": [...] } ] }.
    tree=false : liste plate avec parent_id.
    """
    flat = list_collections()
    if not tree:
        return {"collections": flat}
    by_id = {c["id"]: {**c, "children": []} for c in flat}
    roots = []
    for c in flat:
        node = by_id[c["id"]]
        pid = c.get("parent_id")
        if not pid or pid not in by_id:
            roots.append(node)
        else:
            by_id[pid]["children"].append(node)
    return {"collections": roots}


@router.get("/collections/category-specs")
def list_category_collection_specs():
    """
    Liste toutes les collections « catégorie » à créer (contraintes, univers, secteur, domaine, lots).
    Utiliser en n8n pour créer les collections manquantes (GET /collections puis pour chaque spec
    appeler POST /collections/ensure avec le nom, ou POST /collections si l'id n'est pas dans la liste).
    """
    return {"specs": get_all_category_collection_specs()}


@router.post("/collections/bulk")
def bulk_create_collections_route(payload: CollectionsBulkCreate):
    """
    Crée plusieurs collections en une fois. Body : { "collections": [ { "name": "...", "parent_id": "..."? }, ... ] }.
    Retourne la liste des collections créées (id, name, parent_id).
    """
    created = []
    for c in payload.collections:
        id_ = create_collection(c.name, parent_id=c.parent_id)
        created.append(CollectionOut(id=id_, name=c.name, parent_id=c.parent_id))
    return {"created": created, "count": len(created)}


@router.post("/collections/ensure")
def ensure_collection_route(payload: CollectionCreate):
    """
    Crée la collection seulement si elle n'existe pas encore (vérification par l'id dérivé du nom).
    Retourne { "id": "...", "created": true/false }. Idempotent : appeler avant chaque indexation
    pour s'assurer que la collection existe.
    """
    existing = {c["id"] for c in list_collections()}
    id_ = create_collection(payload.name, parent_id=payload.parent_id)
    created = id_ not in existing
    return {"id": id_, "created": created}


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
    nocodb_record_id: Annotated[str | None, Form()] = None,
    nocodb_table_name: Annotated[str | None, Form()] = None,
    nocodb_base_id: Annotated[str | None, Form()] = None,
    affaire_id: Annotated[str | None, Form()] = None,
    numero_affaire: Annotated[str | None, Form()] = None,
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
    if nocodb_record_id:
        meta["nocodb_record_id"] = nocodb_record_id
    if nocodb_table_name:
        meta["nocodb_table_name"] = nocodb_table_name
    if nocodb_base_id:
        meta["nocodb_base_id"] = nocodb_base_id
    if affaire_id:
        meta["affaire_id"] = affaire_id
    if numero_affaire:
        meta["numero_affaire"] = numero_affaire

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


@router.delete("/collections/{collection_id}")
def delete_collection_route(collection_id: str):
    """Supprime la collection et tout son contenu. Irréversible."""
    try:
        delete_collection(collection_id)
    except Exception as e:
        err = str(e)
        if "does not exist" in err.lower() or "not found" in err.lower():
            raise HTTPException(404, f"Collection non trouvée: {collection_id}")
        raise HTTPException(502, err)
    return {"deleted": collection_id}


@router.delete("/collections/{collection_id}/documents/{document_id:path}")
def delete_document_route(collection_id: str, document_id: str):
    """Supprime tous les chunks d'un document de la collection."""
    try:
        delete_document(collection_id, document_id)
    except Exception as e:
        err = str(e)
        if "does not exist" in err.lower() or "not found" in err.lower():
            raise HTTPException(404, f"Collection non trouvée: {collection_id}")
        raise HTTPException(502, err)
    return {"deleted": document_id, "collection_id": collection_id}


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
    """
    Recherche vectorielle pour l'IA / LLM Mistral.
    include_subcollections=true : cherche dans cette collection et toutes les sous-collections.
    """
    try:
        results = vector_search(
            collection_id,
            payload.query,
            top_k=payload.top_k,
            include_subcollections=payload.include_subcollections,
        )
    except Exception as e:
        raise HTTPException(404, f"Collection non trouvée ou erreur: {e}")
    return {"results": [SearchResult(**r) for r in results]}


# --- Connexions API (sources) : NocoDB, etc. ---


@router.get("/sources", response_model=list[SourceOut])
def list_sources_route():
    """Liste les connexions API configurées (NocoDB, etc.) pour indexer des documents."""
    return list_sources()


@router.get("/sources/{source_id}")
def get_source_route(source_id: str):
    """Détail d'une source (config sans clé API en clair)."""
    s = get_source(source_id)
    if not s:
        raise HTTPException(404, "Source non trouvée")
    cfg = dict(s.get("config", {}))
    if cfg.get("api_key"):
        cfg["api_key"] = "********"
    return {"id": s["id"], "name": s["name"], "type": s["type"], "enabled": s.get("enabled", True), "config": cfg}


@router.post("/sources", response_model=SourceOut)
def create_source_route(payload: SourceCreate):
    """Crée une connexion API (ex. table NocoDB) pour indexer des documents."""
    created = create_source(payload.model_dump())
    if created.get("config", {}).get("api_key"):
        created = {**created, "config": {**created["config"], "api_key": "********"}}
    return SourceOut(**created)


@router.put("/sources/{source_id}")
def update_source_route(source_id: str, payload: SourceUpdate):
    """Met à jour une source (nom, config, enabled)."""
    updated = update_source(source_id, payload.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, "Source non trouvée")
    return updated


@router.delete("/sources/{source_id}")
def delete_source_route(source_id: str):
    """Supprime une connexion API."""
    if not delete_source(source_id):
        raise HTTPException(404, "Source non trouvée")
    return {"deleted": source_id}


@router.post("/sources/{source_id}/sync")
async def sync_source_route(source_id: str):
    """
    Lance la synchronisation : récupère les enregistrements de la source (ex. NocoDB),
    assure les collections et indexe chaque document dans le store vectoriel.
    """
    result = await sync_nocodb_source(source_id)
    if not result.get("ok") and "error" in result:
        raise HTTPException(502, result["error"])
    return result
