"""Routes pour la transcription audio (Mistral) et l'analyse de réunions."""

import json
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from pydantic import BaseModel, Field

from app.config import settings
from app.services.mistral_agent import analyze_with_prompt
from app.services.transcription_service import transcribe_complete, transcribe_stream

router = APIRouter()

MEETING_ANALYSIS_PROMPT = (
    "Tu es un assistant qui analyse des comptes-rendus de réunion. À partir de la transcription suivante, "
    "fournis : 1) un résumé en quelques phrases, 2) les décisions prises, 3) les actions à faire avec les responsables si possible."
)

MAX_AUDIO_BYTES = settings.max_audio_size_mb * 1024 * 1024


async def _get_audio_from_url(file_url: str) -> tuple[bytes, str]:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            r = await client.get(file_url)
            r.raise_for_status()
            if len(r.content) > MAX_AUDIO_BYTES:
                raise HTTPException(
                    400, f"Fichier audio trop volumineux (max {settings.max_audio_size_mb} Mo)"
                )
            filename = r.url.path.split("/")[-1] or "audio"
            if not filename or filename == "/":
                filename = "audio"
            return r.content, filename
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            502, f"Impossible de télécharger le fichier (URL renvoie {e.response.status_code})"
        )
    except httpx.RequestError as e:
        raise HTTPException(502, f"Impossible d'accéder à l'URL: {str(e)}")


async def _read_audio_upload(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read()
    if len(content) > MAX_AUDIO_BYTES:
        raise HTTPException(
            400, f"Fichier audio trop volumineux (max {settings.max_audio_size_mb} Mo)"
        )
    return content, file.filename or "audio"


def _parse_timestamp_granularities(value: str | None) -> list[str] | None:
    if not value or not value.strip():
        return None
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    valid = [p for p in parts if p in ("segment", "word")]
    return valid if valid else None


def _parse_context_bias(value: str | None) -> list[str] | None:
    if not value or not value.strip():
        return None
    return [p.strip() for p in value.split(",") if p.strip()]


@router.post("/transcribe")
async def transcribe_endpoint(
    file: Annotated[UploadFile | None, File()] = None,
    file_url: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    diarize: Annotated[bool, Form()] = False,
    timestamp_granularities: Annotated[str | None, Form()] = None,
    context_bias: Annotated[str | None, Form()] = None,
    analyze_meeting: Annotated[bool, Form()] = False,
):
    """
    Transcription audio via Mistral (fichier ou URL).
    Option analyze_meeting : en plus de la transcription, retourne une analyse (résumé, décisions, actions).
    """
    if file and file.filename:
        content, filename = await _read_audio_upload(file)
    elif file_url:
        content, filename = await _get_audio_from_url(file_url)
    else:
        raise HTTPException(
            400, "Fournir soit un fichier audio (multipart), soit file_url (form)."
        )

    ts_gr = _parse_timestamp_granularities(timestamp_granularities)
    bias = _parse_context_bias(context_bias)

    try:
        result = transcribe_complete(
            file_content=content,
            file_name=filename,
            model=None,
            language=language,
            diarize=diarize,
            timestamp_granularities=ts_gr,
            context_bias=bias,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Erreur Mistral (transcription): {str(e)}")

    if not analyze_meeting:
        return result

    text = result.get("text", "") or ""
    if not text.strip():
        return {"transcript": result, "analysis": "Aucun texte transcrit à analyser."}

    try:
        analysis = analyze_with_prompt(text, prompt=MEETING_ANALYSIS_PROMPT)
    except Exception as e:
        raise HTTPException(502, f"Erreur Mistral (analyse réunion): {str(e)}")

    return {"transcript": result, "analysis": analysis}


@router.post("/transcribe/stream")
async def transcribe_stream_endpoint(
    file: Annotated[UploadFile | None, File()] = None,
    file_url: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    diarize: Annotated[bool, Form()] = False,
    timestamp_granularities: Annotated[str | None, Form()] = None,
    context_bias: Annotated[str | None, Form()] = None,
):
    """
    Transcription audio en streaming (SSE). Mêmes paramètres que POST /transcribe.
    """
    if file and file.filename:
        content, filename = await _read_audio_upload(file)
    elif file_url:
        content, filename = await _get_audio_from_url(file_url)
    else:
        raise HTTPException(
            400, "Fournir soit un fichier audio (multipart), soit file_url (form)."
        )

    ts_gr = _parse_timestamp_granularities(timestamp_granularities)
    bias = _parse_context_bias(context_bias)

    def event_generator():
        try:
            for event in transcribe_stream(
                file_content=content,
                file_name=filename,
                model=None,
                language=language,
                diarize=diarize,
                timestamp_granularities=ts_gr,
                context_bias=bias,
            ):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


class AnalyzeMeetingBody(BaseModel):
    """Corps pour analyser un texte de transcription déjà disponible."""

    transcript_text: str = Field(..., min_length=1, description="Texte de la transcription à analyser")


@router.post("/analyze-meeting")
async def analyze_meeting_endpoint(body: AnalyzeMeetingBody):
    """
    Analyse un texte de transcription déjà disponible (résumé, décisions, actions).
    Utile après une transcription faite ailleurs ou en deux appels (transcribe puis analyze).
    """
    try:
        analysis = analyze_with_prompt(body.transcript_text, prompt=MEETING_ANALYSIS_PROMPT)
    except Exception as e:
        raise HTTPException(502, f"Erreur Mistral (analyse réunion): {str(e)}")
    return {"analysis": analysis}
