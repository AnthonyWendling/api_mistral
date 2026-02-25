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
    async with httpx.AsyncClient(follow_redirects=True) as client:
        r = await client.get(file_url)
        r.raise_for_status()
        if len(r.content) > MAX_BYTES:
            raise HTTPException(400, f"Fichier trop volumineux (max {settings.max_file_size_mb} Mo)")
        filename = r.url.path.split("/")[-1] or "document"
        return r.content, filename


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

    analysis = analyze_document(text)

    indexed = 0
    if add_to_collection_id and text:
        indexed = add_documents(
            add_to_collection_id,
            [text],
            document_id=document_id,
            source_file=filename,
            file_url=file_url or "",
            deduplicate=True,
        )

    return {
        "analysis": analysis,
        "add_to_collection_id": add_to_collection_id,
        "indexed_chunks": indexed,
    }
