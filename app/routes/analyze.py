import io
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import settings
from app.services.extraction import extract_text
from app.services.mistral_agent import analyze_document
from app.services.vector_store_service import add_documents

router = APIRouter()

MAX_BYTES = settings.max_file_size_mb * 1024 * 1024


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


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(400, f"Fichier trop volumineux (max {settings.max_file_size_mb} Mo)")
    return content, file.filename or "document"


@router.post("/document")
async def analyze_document_endpoint(
    file: Annotated[UploadFile | None, File()] = None,
    file_url: Annotated[str | None, Form()] = None,
    add_to_collection_id: Annotated[str | None, Form()] = None,
    document_id: Annotated[str | None, Form()] = None,
):
    if file and file.filename:
        content, filename = await _read_upload(file)
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

    try:
        analysis = analyze_document(text)
    except Exception as e:
        raise HTTPException(502, f"Erreur Mistral (analyse): {str(e)}")

    indexed = 0
    if add_to_collection_id and text:
        try:
            indexed = add_documents(
            add_to_collection_id,
            [text],
            document_id=document_id,
            source_file=filename,
            file_url=file_url or "",
            deduplicate=True,
        )
        except Exception as e:
            pass  # indexation optionnelle, on ne fait pas échouer la requête

    return {
        "analysis": analysis,
        "add_to_collection_id": add_to_collection_id,
        "indexed_chunks": indexed,
    }
