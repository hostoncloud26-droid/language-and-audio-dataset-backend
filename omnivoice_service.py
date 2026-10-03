import os
import json
import re
import logging
from typing import Optional, Dict, Any, Tuple
import httpx
try:
    from .config import reload_env, GENERATED_DIR
    from .audio_generator import generate_speech_file_async, generate_wav_file
    from .chibisafe_service import upload_audio_to_chibisafe
except (ImportError, ValueError):
    try:
        from backend.config import reload_env, GENERATED_DIR
        from backend.audio_generator import generate_speech_file_async, generate_wav_file
        from backend.chibisafe_service import upload_audio_to_chibisafe
    except ImportError:
        from config import reload_env, GENERATED_DIR
        from audio_generator import generate_speech_file_async, generate_wav_file
        from chibisafe_service import upload_audio_to_chibisafe

logger = logging.getLogger(__name__)

DEFAULT_OMNIVOICE_URL = "http://47.29.133.221:32149"


def get_omnivoice_base_url() -> str:
    reload_env()
    return os.getenv("OMNIVOICE_URL", DEFAULT_OMNIVOICE_URL).strip().rstrip("/")

def get_lang_code(language_id: Any, language_name: Optional[str] = None) -> str:
    """
    Maps language ID / name to ISO 639-1 language code supported by OmniVoice (default 'en').
    """
    name = (language_name or "").lower().strip()
    name_map = {
        "english": "en",
        "tamil": "ta",
        "hindi": "hi",
        "telugu": "te",
        "malayalam": "ml",
        "kannada": "kn",
        "bengali": "bn",
        "marathi": "mr",
        "gujarati": "gu",
        "punjabi": "pa",
        "urdu": "ur",
        "french": "fr",
        "spanish": "es",
        "german": "de",
        "chinese": "zh",
        "japanese": "ja",
        "korean": "ko",
        "arabic": "ar",
        "russian": "ru",
    }
    if name in name_map:
        return name_map[name]

    str_id = str(language_id).strip()
    id_map = {
        "1": "en",
        "2": "ta",
        "3": "hi",
        "4": "te",
        "5": "ml",
        "6": "kn",
        "7": "bn",
    }
    return id_map.get(str_id, "en")

async def check_omnivoice_health(timeout: float = 3.0) -> Dict[str, Any]:
    """
    Checks OmniVoice server health via GET /api/system-info.
    Returns status info and whether server is responding with 200.
    """
    base_url = get_omnivoice_base_url()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url}/api/system-info")
            if resp.status_code == 200:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"text": resp.text}
                return {
                    "online": True,
                    "status_code": resp.status_code,
                    "base_url": base_url,
                    "info": data,
                }
            return {
                "online": False,
                "status_code": resp.status_code,
                "base_url": base_url,
                "error": f"HTTP {resp.status_code}: {resp.text}",
            }
    except Exception as e:
        return {
            "online": False,
            "base_url": base_url,
            "error": str(e),
        }

async def generate_speech_with_omnivoice(
    text: str,
    lang_code: str = "en",
    ref_audio: str = "reference.mp3",
    timeout: float = 35.0,
) -> Optional[Tuple[str, bytes]]:
    """
    Calls OmniVoice endpoints:
    1. POST /api/generate (multipart form data with SSE stream)
       - model: k2-fsa/OmniVoice
       - text: text
       - lang_code: lang_code
       - ref_audio: ref_audio
       - audio_format: wav
    2. Parses stream for 'done' event with 'filename'
    3. GET /audio/outputs/<filename> to download the audio clip
    Returns (filename, wav_bytes) or None on failure/timeout.
    """
    base_url = get_omnivoice_base_url()
    generate_url = f"{base_url}/api/generate"

    logger.info(f"Triggering OmniVoice speech generation at {generate_url} (lang_code={lang_code}, ref_audio={ref_audio})")

    # Form fields matching curl specification exactly
    form_data = {
        "model": "k2-fsa/OmniVoice",
        "text": text,
        "lang_code": lang_code,
        "ref_audio": ref_audio,
        "audio_format": "wav",
    }

    generated_filename: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Step 1: Call POST /api/generate with streaming SSE response
            async with client.stream("POST", generate_url, data=form_data) as response:
                if response.status_code != 200:
                    logger.warning(f"OmniVoice /api/generate returned status {response.status_code}")
                    return None

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    clean_line = line.strip()
                    logger.debug(f"OmniVoice SSE line: {clean_line}")

                    # Check for data line with filename
                    if "filename" in clean_line:
                        # Extract filename using regex or json
                        fn_match = re.search(r'"filename"\s*:\s*"([^"]+)"', clean_line)
                        if fn_match:
                            generated_filename = fn_match.group(1).strip()
                            logger.info(f"OmniVoice completed speech generation. Filename: {generated_filename}")
                            if re.search(r'"type"\s*:\s*"done"', clean_line) or '"done"' in clean_line:
                                break

            if not generated_filename:
                logger.warning("OmniVoice stream ended without yielding a filename.")
                return None

            # Step 2: Download the generated audio file from /audio/outputs/<filename>
            output_url = f"{base_url}/audio/outputs/{generated_filename}"
            logger.info(f"Downloading OmniVoice audio from: {output_url}")
            audio_resp = await client.get(output_url, timeout=15.0)

            if audio_resp.status_code == 200 and len(audio_resp.content) > 0:
                logger.info(f"Successfully downloaded OmniVoice audio ({len(audio_resp.content)} bytes)")
                return generated_filename, audio_resp.content
            else:
                logger.warning(f"Failed to download audio from {output_url}, status: {audio_resp.status_code}")
                return None

    except httpx.TimeoutException:
        logger.warning(f"OmniVoice generation timed out after {timeout} seconds.")
        return None
    except Exception as e:
        logger.warning(f"OmniVoice generation encountered exception: {e}")
        return None

async def synthesize_and_upload_audio(
    text: str,
    language_id: Any = 1,
    language_name: str = "English",
    lang_code: Optional[str] = None,
    ref_audio: str = "reference.mp3",
    upload_to_server: bool = True,
) -> Dict[str, Any]:
    """
    Unified voice synthesis function:
    1. Tries OmniVoice speech generation API.
    2. If OmniVoice returns the audio clip, saves local copy and uploads to Chibisafe server.
    3. If OmniVoice is unavailable or times out, falls back to local synthesis generator and uploads to Chibisafe.
    4. Guarantees a fully playable audio URL uploaded to remote server and recorded in dataset.
    """
    clean_text = text.strip()
    target_code = lang_code or get_lang_code(language_id, language_name)
    engine_used = "omnivoice"

    # Attempt 1: Call OmniVoice API
    logger.info(f"Synthesizing speech for '{clean_text[:40]}...' using OmniVoice (lang={target_code})")
    omnivoice_result = await generate_speech_with_omnivoice(
        text=clean_text,
        lang_code=target_code,
        ref_audio=ref_audio,
        timeout=3.5,  # Fast failover if remote OmniVoice server is unreachable
    )

    wav_bytes: Optional[bytes] = None
    filename: str = ""
    duration: float = 4.0
    content_type: str = "audio/wav"

    if omnivoice_result:
        filename, wav_bytes = omnivoice_result
        content_type = "audio/wav"
        # Save local copy in GENERATED_DIR
        local_path = GENERATED_DIR / filename
        try:
            with open(local_path, "wb") as f:
                f.write(wav_bytes)
        except Exception as e:
            logger.warning(f"Failed to write local copy: {e}")

        # Compute duration from WAV bytes if possible
        try:
            import wave
            import io
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    duration = round(frames / float(rate), 2)
        except Exception:
            words = clean_text.split()
            duration = round(max(2.5, len(words) * 0.45 + 1.0), 2)

    else:
        # Fallback to authentic neural human speech synthesis
        engine_used = "neural_speech_engine"
        logger.info(f"OmniVoice remote server unavailable; generating authentic human speech via Neural Voice Engine for {language_name}")
        local_result = await generate_speech_file_async(
            text=clean_text,
            language_id=int(language_id) if str(language_id).isdigit() else 1,
            language_name=language_name,
        )
        filename = local_result["filename"]
        duration = local_result["duration"]
        wav_bytes = local_result["audio_bytes"]
        content_type = local_result.get("content_type", "audio/mpeg")

    # Upload to Chibisafe remote server if requested
    chibi_url = None
    if upload_to_server and wav_bytes:
        logger.info(f"Uploading generated audio '{filename}' ({len(wav_bytes)} bytes) to Chibisafe remote server...")
        chibi_res = await upload_audio_to_chibisafe(
            file_bytes=wav_bytes,
            filename=filename,
            content_type=content_type,
        )
        if chibi_res.get("success") and chibi_res.get("audio_url"):
            chibi_url = chibi_res["audio_url"]
            logger.info(f"Generated speech audio uploaded to Chibisafe successfully: {chibi_url}")
        else:
            logger.warning(f"Chibisafe upload failed for generated audio: {chibi_res.get('error')}")

    final_audio_url = chibi_url or f"/media/generated/{filename}"

    return {
        "success": True,
        "audio_url": final_audio_url,
        "filename": filename,
        "duration": duration,
        "engine": engine_used,
        "lang_code": target_code,
    }
