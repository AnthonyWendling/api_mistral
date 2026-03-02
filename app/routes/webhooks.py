"""
Webhooks pour : RAG (question + vecteurs → réponse), recherche document pour téléchargement,
suggestion de collections à partir des dossiers SharePoint, etc.
"""

import json
import re
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.schemas.requests_responses import RAGRequest, RAGResponse, SearchResult
from app.services.mistral_agent import rag_answer, suggest_collections_from_folders
from app.services.vector_store_service import search as vector_search

router = APIRouter()


class FolderItem(BaseModel):
    """Un dossier (ex. sortie SharePoint List get many). path ou webUrl ou id permet de l'identifier."""
    model_config = {"populate_by_name": True}
    name: str = Field(..., description="Nom du dossier (ex. displayName ou name)")
    path: str | None = Field(None, description="Chemin (ex. /teams/Affaires/MonDossier). Optionnel si webUrl ou id fourni.")
    web_url: str | None = Field(None, alias="webUrl", description="URL complète du dossier SharePoint")
    id: str | None = Field(None, description="ID SharePoint du dossier/site")


class SuggestCollectionsRequest(BaseModel):
    """Liste des dossiers SharePoint pour que l'IA propose les meilleures collections."""
    folders: list[FolderItem] = Field(..., min_length=1)


class SearchDocumentsRequest(BaseModel):
    """Recherche sémantique + retour des documents uniques (pour savoir lequel télécharger)."""
    query: str = Field(..., min_length=1)
    collection_id: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=50)


@router.post("/suggest-collections")
async def suggest_collections_webhook(request: Request):
    """
    Webhook : envoie la liste de tous les dossiers SharePoint → l'IA propose les meilleures
    collections à créer dans l'API (nom, description, quels dossiers y affecter) pour que
    l'IA apprenne de façon structurée.
    Accepte soit un objet { "folders": [...] } soit directement un tableau [ {...}, ... ].
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(422, "Body must be valid JSON")

    if isinstance(body, list):
        folders_list = body
    elif isinstance(body, dict) and "folders" in body:
        folders_list = body["folders"]
    else:
        raise HTTPException(
            422,
            'Body must be { "folders": [ { "name", "webUrl"?, "id"? }, ... ] } or directly an array of folder objects.',
        )

    if not folders_list:
        raise HTTPException(422, "At least one folder required")

    try:
        folders = [FolderItem.model_validate(f) for f in folders_list]
    except Exception as e:
        raise HTTPException(422, f"Invalid folder item: {e}")

    def _path_or_id(f: FolderItem) -> str:
        if f.path:
            return f.path
        if f.web_url:
            return urlparse(f.web_url).path or f.name
        return f.id or f.name

    folders_text = "\n".join(f"{_path_or_id(f)} | {f.name}" for f in folders)
    try:
        raw = suggest_collections_from_folders(folders_text)
    except Exception as e:
        raise HTTPException(502, f"Erreur Mistral: {str(e)}")

    # Tenter d'extraire du JSON pour renvoyer une structure exploitable
    collections_parsed = None
    try:
        # Le modèle peut renvoyer du texte autour du JSON ; on tente d'extraire un bloc {...}
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            data = json.loads(match.group())
            collections_parsed = data.get("collections", data) if isinstance(data, dict) else data
    except json.JSONDecodeError:
        pass

    return {
        "suggestion": raw,
        "collections": collections_parsed,
        "folder_count": len(folders),
    }


@router.post("/rag", response_model=RAGResponse)
def rag_webhook(payload: RAGRequest):
    """
    Webhook RAG : envoie une question + collection_id → recherche vectorielle
    → contexte envoyé à Mistral → réponse fiable basée sur tes documents.
    """
    try:
        results = vector_search(
            payload.collection_id,
            payload.query,
            top_k=payload.top_k,
        )
    except Exception as e:
        err = str(e)
        if "does not exist" in err.lower() or "not found" in err.lower():
            raise HTTPException(404, f"Collection non trouvée: {payload.collection_id}")
        raise HTTPException(502, f"Erreur recherche vectorielle: {err}")

    if not results:
        return RAGResponse(
            answer="Aucun document pertinent trouvé dans la base. Reformule ou vérifie la collection.",
            sources=[],
        )

    context = "\n\n---\n\n".join(r["text"] for r in results)

    try:
        answer = rag_answer(context, payload.query, system_prompt=payload.system_prompt)
    except Exception as e:
        raise HTTPException(502, f"Erreur Mistral (RAG): {str(e)}")

    return RAGResponse(
        answer=answer,
        sources=[SearchResult(**r) for r in results],
    )


@router.post("/search-documents")
def search_documents_webhook(payload: SearchDocumentsRequest):
    """
    Webhook : recherche sémantique dans la collection puis retourne les chunks
    + la liste des documents uniques concernés (source_file, file_url) pour téléchargement.
    """
    try:
        results = vector_search(
            payload.collection_id,
            payload.query,
            top_k=payload.top_k,
        )
    except Exception as e:
        err = str(e)
        if "does not exist" in err.lower() or "not found" in err.lower():
            raise HTTPException(404, f"Collection non trouvée: {payload.collection_id}")
        raise HTTPException(502, f"Erreur recherche: {err}")

    # Documents uniques (pour retrouver le bon dossier/fichier SharePoint)
    seen = set()
    documents = []
    for r in results:
        meta = r.get("metadata") or {}
        doc_id = meta.get("document_id") or meta.get("source_file") or ""
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            doc = {
                "document_id": doc_id,
                "source_file": meta.get("source_file", ""),
                "file_url": meta.get("file_url", ""),
            }
            if meta.get("folder_path"):
                doc["folder_path"] = meta["folder_path"]
            if meta.get("sharepoint_item_id"):
                doc["sharepoint_item_id"] = meta["sharepoint_item_id"]
            if meta.get("drive_id"):
                doc["drive_id"] = meta["drive_id"]
            if meta.get("site_id"):
                doc["site_id"] = meta["site_id"]
            if meta.get("nocodb_record_id"):
                doc["nocodb_record_id"] = meta["nocodb_record_id"]
            if meta.get("nocodb_table_name"):
                doc["nocodb_table_name"] = meta["nocodb_table_name"]
            if meta.get("nocodb_base_id"):
                doc["nocodb_base_id"] = meta["nocodb_base_id"]
            documents.append(doc)

    return {
        "results": [SearchResult(**r) for r in results],
        "documents": documents,
        "query": payload.query,
        "collection_id": payload.collection_id,
    }
