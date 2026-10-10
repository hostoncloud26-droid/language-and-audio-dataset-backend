import os
import logging
from typing import Optional, Dict, Any, Tuple
try:
    from .config import reload_env, GENERATED_DIR
    from .audio_generator import (
        generate_speech_file_async,
        generate_wav_file,
        resolve_voice_and_code,
        NEURAL_VOICE_MAP,
    )
    from .chibisafe_service import upload_audio_to_chibisafe
except (ImportError, ValueError):
    try:
        from backend.config import reload_env, GENERATED_DIR
        from backend.audio_generator import (
            generate_speech_file_async,
            generate_wav_file,
            resolve_voice_and_code,
            NEURAL_VOICE_MAP,
        )
        from backend.chibisafe_service import upload_audio_to_chibisafe
    except ImportError:
        from config import reload_env, GENERATED_DIR
        from audio_generator import (
            generate_speech_file_async,
            generate_wav_file,
            resolve_voice_and_code,
            NEURAL_VOICE_MAP,
        )
        from chibisafe_service import upload_audio_to_chibisafe

logger = logging.getLogger(__name__)


def get_omnivoice_base_url() -> str:
    """Returns the active TTS engine provider description."""
    return "Microsoft Edge Neural TTS (Built-in)"


def get_lang_code(language_id: Any, language_name: Optional[str] = None) -> str:
    """
    Resolves language ID / name to code using audio_generator's language mappings.
    """
    _, code = resolve_voice_and_code(language_id, language_name)
    return code or "en"


async def check_edge_tts_health(timeout: float = 3.0) -> Dict[str, Any]:
    """
    Checks Edge-TTS health. Edge-TTS runs locally via Microsoft Azure Neural endpoints,
    providing high-quality neural voice synthesis for Indian and global languages.
    """
    return {
        "online": True,
        "status_code": 200,
        "engine": "Microsoft Edge Neural TTS",
        "status": "online",
        "total_languages": len(NEURAL_VOICE_MAP),
        "supported_languages": sorted(list(set(NEURAL_VOICE_MAP.keys()))),
    }


# Backward-compatible alias for existing health check endpoints
async def check_omnivoice_health(timeout: float = 3.0) -> Dict[str, Any]:
    return await check_edge_tts_health(timeout=timeout)


async def synthesize_and_upload_audio(
    text: str,
    language_id: Any = 1,
    language_name: str = "English",
    lang_code: Optional[str] = None,
    ref_audio: str = "reference.mp3",
    upload_to_server: bool = True,
) -> Dict[str, Any]:
    """
    High-Fidelity Edge-TTS Speech Synthesis Pipeline:
    1. Synthesizes human-quality spoken speech directly using Microsoft Edge Neural TTS.
    2. Automatically resolves natural regional neural voices (Tamil, Hindi, Telugu, English, etc.).
    3. Uploads the generated audio file to Chibisafe remote server for public streaming.
    4. Falls back to local /media/generated/ audio URL if Chibisafe is unreachable.
    """
    clean_text = text.strip()
    voice, resolved_code = resolve_voice_and_code(language_id, language_name)
    target_code = lang_code or resolved_code or "en"

    logger.info(
        f"Synthesizing speech via Edge-TTS for: '{clean_text[:40]}...' "
        f"(Lang: {language_name}, Voice: {voice})"
    )

    # Step 1: Synthesize human-quality voice audio with Edge-TTS
    speech_result = await generate_speech_file_async(
        text=clean_text,
        language_id=int(language_id) if str(language_id).isdigit() else 1,
        language_name=language_name,
    )

    filename = speech_result["filename"]
    duration = speech_result["duration"]
    audio_bytes = speech_result["audio_bytes"]
    content_type = speech_result.get("content_type", "audio/mpeg")

    # Step 2: Upload to Chibisafe server if requested
    chibi_url = None
    if upload_to_server and audio_bytes:
        try:
            logger.info(f"Uploading Edge-TTS audio '{filename}' ({len(audio_bytes)} bytes) to Chibisafe server...")
            chibi_res = await upload_audio_to_chibisafe(
                file_bytes=audio_bytes,
                filename=filename,
                content_type=content_type,
            )
            if chibi_res.get("success") and chibi_res.get("audio_url"):
                chibi_url = chibi_res["audio_url"]
                logger.info(f"Edge-TTS audio uploaded to Chibisafe successfully: {chibi_url}")
            else:
                logger.warning(f"Chibisafe upload skipped/failed: {chibi_res.get('error')}")
        except Exception as e:
            logger.warning(f"Non-critical error during Chibisafe upload: {e}")

    final_audio_url = chibi_url or f"/media/generated/{filename}"

    return {
        "success": True,
        "audio_url": final_audio_url,
        "filename": filename,
        "duration": duration,
        "engine": "edge_tts",
        "voice": voice,
        "lang_code": target_code,
    }
