"""System diagnostics: observed state only.

Every value here is either measured on request or read from configuration. Nothing is
estimated or defaulted to "healthy". Configuration is reported by name and whether it is
set, never by value.
"""

import asyncio
import os
from typing import Any, Callable, Dict, List

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from backend.friday.config import settings

router = APIRouter(tags=["Diagnostics"])

# Wired by app.py to avoid import cycles.
_deps: Dict[str, Any] = {}


def configure(**deps: Any) -> None:
    _deps.update(deps)


def _state(ok: bool, degraded: bool = False) -> str:
    return "available" if ok and not degraded else "degraded" if ok else "unavailable"


@router.get("/diagnostics")
@router.get("/api/diagnostics")
async def diagnostics() -> Dict[str, Any]:
    adapter = _deps["ollama_adapter"]
    voice_service_getter: Callable[[], Any] = _deps["voice_service"]
    world_service = _deps["world_service"]
    memory_store = _deps["memory_store"]
    location_service = _deps["location_service"]

    models_task = asyncio.create_task(adapter.list_models())
    world_task = asyncio.create_task(world_service.get_status())
    voice = voice_service_getter()
    voice_cfg = await run_in_threadpool(voice.get_config)
    models = await models_task
    try:
        world = (await world_task).model_dump()
    except Exception as exc:  # report, don't hide
        world = {"status": "unknown", "error": str(exc), "providers": {}}

    model_installed = None if models is None else any(
        m == settings.model_name or m.split(":")[0] == settings.model_name and ":" not in settings.model_name for m in models
    )
    try:
        memory_count = len(memory_store.list())
        memory_state = "available"
    except Exception:
        memory_count, memory_state = None, "unavailable"

    loc = location_service.get_status()
    warnings: List[Dict[str, str]] = []
    if models is not None and not model_installed:
        warnings.append({"level": "error", "message": f"Configured model '{settings.model_name}' is not installed. Run: ollama pull {settings.model_name}"})
    if settings.stt_provider not in ("windows_sapi", "faster_whisper"):
        warnings.append({"level": "warning", "message": f"FRIDAY_STT_PROVIDER='{settings.stt_provider}' is not a known engine, so Windows Speech is the default."})
    elif not voice_cfg.stt_available:
        warnings.append({"level": "error", "message": f"The default speech engine '{voice_cfg.stt_engine}' is not available. See docs/overhaul/handoff.md."})
    if settings.location_provider == "osm" and not settings.osm_contact_email:
        warnings.append({"level": "info", "message": "OSM_CONTACT_EMAIL is not set. Nominatim's usage policy asks clients to identify a contact."})
    if not settings.firms_map_key:
        warnings.append({"level": "info", "message": "FIRMS_MAP_KEY is not set, so the active-fires layer is disabled."})
    if settings.location_provider == "google" and not settings.google_maps_api_key:
        warnings.append({"level": "warning", "message": "LOCATION_PROVIDER=google but GOOGLE_MAPS_API_KEY is not set."})

    return {
        "backend": {
            "state": "available",
            "version": settings.version,
            "bind_host": settings.host,
            "loopback_only": settings.host in ("127.0.0.1", "localhost", "::1"),
        },
        "model": {
            "state": "unavailable" if models is None else _state(True, degraded=not model_installed),
            "runtime": "Ollama",
            "base_url": settings.ollama_base_url,
            "configured": settings.model_name,
            "installed": model_installed,
            "installed_models": models or [],
            "request_timeout_s": settings.request_timeout_seconds,
        },
        "voice": {
            "stt_state": _state(voice_cfg.stt_available),
            "tts_state": _state(voice_cfg.tts_available),
            "stt_engine": voice_cfg.stt_engine,
            "tts_engine": voice_cfg.tts_engine,
            "stt_language": settings.stt_language,
            "recognizers": voice_cfg.installed_speech_packs,
            "voices": voice_cfg.available_voices,
            "wake_word_active": voice_cfg.wake_word_active,
            "max_clip_seconds": settings.max_audio_duration_seconds,
        },
        "location": {
            "provider": settings.location_provider,
            "tracking_enabled": loc.tracking_enabled,
            "fix_status": loc.latest_fix.status if loc.latest_fix else None,
        },
        "memory": {"state": memory_state, "active_records": memory_count, "path": str(settings.memory_db_path)},
        "world": world,
        "config": {
            name: bool(os.environ.get(name))
            for name in ("LOCATION_PROVIDER", "GOOGLE_MAPS_API_KEY", "FIRMS_MAP_KEY", "OSM_CONTACT_EMAIL", "FRIDAY_STT_LANGUAGE", "FRIDAY_MEMORY_DB")
        },
        "warnings": warnings,
    }
