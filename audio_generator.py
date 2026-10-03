import os
import io
import time
import uuid
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import edge_tts
from gtts import gTTS
try:
    from .config import GENERATED_DIR
except (ImportError, ValueError):
    try:
        from backend.config import GENERATED_DIR
    except ImportError:
        from config import GENERATED_DIR

logger = logging.getLogger(__name__)

# High-quality neural voices per language
NEURAL_VOICE_MAP = {
    # English
    "english": "en-US-JennyNeural",
    "en": "en-US-JennyNeural",
    # Tamil
    "tamil": "ta-IN-PallaviNeural",
    "ta": "ta-IN-PallaviNeural",
    # Hindi
    "hindi": "hi-IN-SwaraNeural",
    "hi": "hi-IN-SwaraNeural",
    # Telugu
    "telugu": "te-IN-ShrutiNeural",
    "te": "te-IN-ShrutiNeural",
    # Malayalam
    "malayalam": "ml-IN-SobhanaNeural",
    "ml": "ml-IN-SobhanaNeural",
    # Kannada
    "kannada": "kn-IN-SapnaNeural",
    "kn": "kn-IN-SapnaNeural",
    # Bengali
    "bengali": "bn-IN-TanishaaNeural",
    "bn": "bn-IN-TanishaaNeural",
    # Marathi
    "marathi": "mr-IN-AarohiNeural",
    "mr": "mr-IN-AarohiNeural",
    # Gujarati
    "gujarati": "gu-IN-DhwaniNeural",
    "gu": "gu-IN-DhwaniNeural",
    # French
    "french": "fr-FR-DeniseNeural",
    "fr": "fr-FR-DeniseNeural",
    # Spanish
    "spanish": "es-ES-ElviraNeural",
    "es": "es-ES-ElviraNeural",
    # German
    "german": "de-DE-KatjaNeural",
    "de": "de-DE-KatjaNeural",
}

GTTS_LANG_MAP = {
    "english": "en",
    "en": "en",
    "tamil": "ta",
    "ta": "ta",
    "hindi": "hi",
    "hi": "hi",
    "telugu": "te",
    "te": "te",
    "malayalam": "ml",
    "ml": "ml",
    "kannada": "kn",
    "kn": "kn",
    "bengali": "bn",
    "bn": "bn",
    "marathi": "mr",
    "mr": "mr",
    "gujarati": "gu",
    "gu": "gu",
    "french": "fr",
    "fr": "fr",
    "spanish": "es",
    "es": "es",
    "german": "de",
    "de": "de",
}

def resolve_voice_and_code(language_id: Any, language_name: Optional[str] = None) -> Tuple[str, str]:
    name = (language_name or "").lower().strip()
    lid = str(language_id).strip()

    if name in NEURAL_VOICE_MAP:
        return NEURAL_VOICE_MAP[name], GTTS_LANG_MAP.get(name, "en")
    
    # Check by language ID
    id_map = {
        "1": ("en-US-JennyNeural", "en"),
        "2": ("ta-IN-PallaviNeural", "ta"),
        "3": ("hi-IN-SwaraNeural", "hi"),
        "4": ("te-IN-ShrutiNeural", "te"),
        "5": ("ml-IN-SobhanaNeural", "ml"),
        "6": ("kn-IN-SapnaNeural", "kn"),
        "7": ("bn-IN-TanishaaNeural", "bn"),
    }
    return id_map.get(lid, ("en-US-JennyNeural", "en"))

async def synthesize_neural_speech(text: str, voice: str) -> Optional[bytes]:
    """
    Synthesizes natural, crystal-clear spoken speech using Microsoft Edge Neural TTS.
    """
    try:
        comm = edge_tts.Communicate(text, voice)
        audio_stream = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                audio_stream.extend(chunk["data"])
        if len(audio_stream) > 0:
            return bytes(audio_stream)
    except Exception as e:
        logger.warning(f"Edge-TTS synthesis error with voice {voice}: {e}")
    return None

def synthesize_gtts_speech(text: str, lang_code: str) -> Optional[bytes]:
    """
    Secondary fallback: Generates speech using Google Text-to-Speech (gTTS).
    """
    try:
        tts = gTTS(text=text, lang=lang_code, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp.read()
    except Exception as e:
        logger.warning(f"gTTS synthesis error with lang {lang_code}: {e}")
    return None

async def generate_speech_file_async(
    text: str,
    language_id: Any = 1,
    language_name: str = "English",
) -> Dict[str, Any]:
    """
    Synthesizes authentic spoken human audio of the provided text.
    Returns metadata including filename, filepath, duration, and audio_url.
    """
    clean_text = text.strip()
    voice, gtts_code = resolve_voice_and_code(language_id, language_name)
    words = clean_text.split()
    estimated_duration = max(2.0, round(len(words) * 0.45 + 0.8, 2))

    filename = f"speech_{language_name.lower()}_{int(time.time())}_{uuid.uuid4().hex[:6]}.mp3"
    file_path = GENERATED_DIR / filename

    logger.info(f"Synthesizing genuine human speech for text: '{clean_text[:50]}...' (Voice: {voice})")

    # Step 1: Try high-fidelity Edge Neural TTS
    audio_bytes = await synthesize_neural_speech(clean_text, voice)

    # Step 2: Try gTTS if Edge-TTS fails
    if not audio_bytes or len(audio_bytes) < 100:
        logger.info(f"Falling back to gTTS with language code: {gtts_code}")
        audio_bytes = synthesize_gtts_speech(clean_text, gtts_code)

    if not audio_bytes:
        raise RuntimeError("Failed to synthesize spoken voice audio through all TTS engines.")

    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    return {
        "filename": filename,
        "filepath": str(file_path),
        "audio_bytes": audio_bytes,
        "audio_url": f"/media/generated/{filename}",
        "duration": estimated_duration,
        "content_type": "audio/mpeg",
    }

def generate_wav_file(text: str, language_id: int = 1, language_name: str = "English", **kwargs) -> dict:
    """
    Synchronous compatibility wrapper that runs real speech synthesis.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(asyncio.run, generate_speech_file_async(text, language_id, language_name)).result()
                return result
        else:
            return loop.run_until_complete(generate_speech_file_async(text, language_id, language_name))
    except Exception:
        # Fallback to direct synchronous gTTS
        _, gtts_code = resolve_voice_and_code(language_id, language_name)
        audio_bytes = synthesize_gtts_speech(text.strip(), gtts_code)
        filename = f"speech_{language_name.lower()}_{int(time.time())}_{uuid.uuid4().hex[:6]}.mp3"
        file_path = GENERATED_DIR / filename
        with open(file_path, "wb") as f:
            f.write(audio_bytes or b"")
        return {
            "filename": filename,
            "filepath": str(file_path),
            "audio_bytes": audio_bytes or b"",
            "audio_url": f"/media/generated/{filename}",
            "duration": max(2.0, round(len(text.split()) * 0.45 + 0.8, 2)),
            "content_type": "audio/mpeg",
        }
