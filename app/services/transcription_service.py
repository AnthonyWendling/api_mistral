"""Service de transcription audio via l'API Mistral (complete + stream)."""

import io
from typing import Any, Iterator

from app.services.mistral_agent import get_client


def transcribe_complete(
    *,
    file_content: bytes | None = None,
    file_name: str | None = None,
    file_url: str | None = None,
    file_id: str | None = None,
    model: str | None = None,
    language: str | None = None,
    diarize: bool = False,
    timestamp_granularities: list[str] | None = None,
    context_bias: list[str] | None = None,
) -> dict[str, Any]:
    """
    Transcription audio complète via Mistral.
    Fournir exactement une source : (file_content + file_name), file_url, ou file_id.
    """
    from app.config import settings

    client = get_client()
    model = model or settings.transcription_model

    kwargs: dict[str, Any] = {"model": model}
    if file_url:
        kwargs["file_url"] = file_url
    elif file_id:
        kwargs["file_id"] = file_id
    elif file_content is not None and file_name:
        kwargs["file"] = {
            "content": io.BytesIO(file_content),
            "file_name": file_name,
        }
    else:
        raise ValueError("Fournir file_content+file_name, file_url ou file_id.")

    if language is not None:
        kwargs["language"] = language
    if diarize:
        kwargs["diarize"] = True
    if timestamp_granularities:
        kwargs["timestamp_granularities"] = timestamp_granularities
    if context_bias:
        kwargs["context_bias"] = context_bias

    response = client.audio.transcriptions.complete(**kwargs)

    # Normaliser la réponse en dict pour la sérialisation JSON
    out: dict[str, Any] = {
        "text": getattr(response, "text", None) or "",
        "language": getattr(response, "language", None),
        "model": getattr(response, "model", None),
        "usage": _usage_to_dict(getattr(response, "usage", None)),
    }
    segments = getattr(response, "segments", None)
    if segments is not None:
        out["segments"] = [
            {
                "text": getattr(s, "text", ""),
                "start": getattr(s, "start", None),
                "end": getattr(s, "end", None),
                "speaker_id": getattr(s, "speaker_id", None),
            }
            for s in segments
        ]
    else:
        out["segments"] = []
    return out


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    return {
        "prompt_audio_seconds": getattr(usage, "prompt_audio_seconds", None),
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def transcribe_stream(
    *,
    file_content: bytes | None = None,
    file_name: str | None = None,
    file_url: str | None = None,
    file_id: str | None = None,
    model: str | None = None,
    language: str | None = None,
    diarize: bool = False,
    timestamp_granularities: list[str] | None = None,
    context_bias: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Transcription audio en streaming (SSE). Yield des événements au format dict.
    Fournir exactement une source : (file_content + file_name), file_url, ou file_id.
    """
    from app.config import settings

    client = get_client()
    model = model or settings.transcription_model

    kwargs: dict[str, Any] = {"model": model}
    if file_url:
        kwargs["file_url"] = file_url
    elif file_id:
        kwargs["file_id"] = file_id
    elif file_content is not None and file_name:
        kwargs["file"] = {
            "content": io.BytesIO(file_content),
            "file_name": file_name,
        }
    else:
        raise ValueError("Fournir file_content+file_name, file_url ou file_id.")

    if language is not None:
        kwargs["language"] = language
    if diarize:
        kwargs["diarize"] = True
    if timestamp_granularities:
        kwargs["timestamp_granularities"] = timestamp_granularities
    if context_bias:
        kwargs["context_bias"] = context_bias

    stream = client.audio.transcriptions.stream(**kwargs)
    # Le SDK peut retourner un context manager (with res as event_stream)
    if hasattr(stream, "__enter__"):
        with stream as event_stream:
            for event in event_stream:
                yield _event_to_dict(event)
    else:
        for event in stream:
            yield _event_to_dict(event)


def _event_to_dict(event: Any) -> dict[str, Any]:
    """Convertit un événement Mistral en dict sérialisable."""
    if hasattr(event, "model_dump"):
        return event.model_dump()
    if hasattr(event, "dict"):
        return event.dict()
    if isinstance(event, dict):
        return event
    return {"raw": str(event)}
