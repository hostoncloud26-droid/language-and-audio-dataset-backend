import os
import re
import logging
from typing import Optional, Dict, Any, List
import httpx

try:
    from .config import reload_env
except (ImportError, ValueError):
    try:
        from backend.config import reload_env
    except ImportError:
        from config import reload_env

logger = logging.getLogger(__name__)

DEFAULT_CHIBISAFE_URL = "http://chibisafe-js70kfifmck6m9b4lzbe5hko.72.61.239.30.sslip.io"
DEFAULT_CHIBISAFE_API_KEY = "QxDWe5hxUn5RtMp6cUFmqrNYZZDJQovV0p7I4KHM0mEzysVGS9vy4S4n8SpEUA6x"
DEFAULT_CHIBISAFE_ALBUM_UUID = "63219c42-774f-4eae-8448-7e75d446a63a"

def get_chibisafe_config():
    reload_env()
    base_url = os.getenv("CHIBISAFE_URL", DEFAULT_CHIBISAFE_URL).strip().rstrip("/")
    api_key = os.getenv("CHIBISAFE_API_KEY", DEFAULT_CHIBISAFE_API_KEY).strip()
    album_uuid = os.getenv("CHIBISAFE_ALBUM_UUID", DEFAULT_CHIBISAFE_ALBUM_UUID).strip()
    return base_url, api_key, album_uuid

def extract_chibisafe_uuid(text_or_url: str) -> Optional[str]:
    """
    Extracts standard UUID (e.g. dc6cc8a8-9c26-418a-9323-beb012696eff)
    from Chibisafe URL or identifier string.
    """
    if not text_or_url:
        return None
    match = re.search(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', str(text_or_url))
    return match.group(0) if match else None

async def upload_audio_to_chibisafe(
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
    album_uuid: Optional[str] = None,
    timeout: float = 20.0
) -> Dict[str, Any]:
    """
    Uploads an audio file directly to the remote Chibisafe server using the REST API:
    - POST /api/upload with header `x-api-key`
    - Associates the uploaded file with the designated album via POST /api/files/album/add
    - Returns the public accessible direct download / audio stream URL.
    """
    base_url, api_key, default_album = get_chibisafe_config()
    target_album = album_uuid or default_album

    if not base_url or not api_key:
        return {
            "success": False,
            "error": "Chibisafe URL or API key is not configured.",
        }

    mime = content_type
    if not mime:
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
            ".webm": "audio/webm",
            ".aac": "audio/aac",
        }
        mime = mime_map.get(ext, "audio/wav")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Step 1: Upload file to Chibisafe
            upload_headers = {
                "x-api-key": api_key,
            }
            files = {
                "file": (filename, file_bytes, mime)
            }
            logger.info(f"Uploading file '{filename}' ({len(file_bytes)} bytes) to Chibisafe at {base_url}/api/upload")
            
            upload_resp = await client.post(
                f"{base_url}/api/upload",
                headers=upload_headers,
                files=files
            )

            if upload_resp.status_code != 200:
                err_msg = f"Chibisafe upload failed with status {upload_resp.status_code}: {upload_resp.text}"
                logger.error(err_msg)
                return {"success": False, "error": err_msg}

            data = upload_resp.json()
            file_uuid = data.get("uuid")
            file_name = data.get("name")

            if not file_uuid:
                err_msg = f"Chibisafe upload did not return file uuid: {data}"
                logger.error(err_msg)
                return {"success": False, "error": err_msg}

            # Step 2: Add to Album (POST /api/files/album/add)
            if target_album:
                try:
                    album_payload = [{"album": target_album, "files": [file_uuid]}]
                    album_resp = await client.post(
                        f"{base_url}/api/files/album/add",
                        headers={"x-api-key": api_key, "Content-Type": "application/json"},
                        json=album_payload
                    )
                    logger.info(f"Added file {file_uuid} to album {target_album}: status {album_resp.status_code}")
                except Exception as alb_err:
                    logger.warning(f"Non-critical error adding file to album: {alb_err}")

            # Public URL to stream/play/download the audio file
            public_audio_url = f"{base_url}/api/file/{file_uuid}/download"

            return {
                "success": True,
                "uuid": file_uuid,
                "name": file_name,
                "audio_url": public_audio_url,
                "album_uuid": target_album,
                "raw_response": data,
            }

    except Exception as e:
        logger.error(f"Exception during Chibisafe upload: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }

async def delete_file_from_chibisafe(file_uuid_or_url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """
    Deletes an uploaded file from the remote Chibisafe server:
    - Calls DELETE /api/file/{uuid} with header `x-api-key`
    - Also handles bulk /api/files/delete if needed
    """
    file_uuid = extract_chibisafe_uuid(file_uuid_or_url)
    if not file_uuid:
        return {"success": False, "error": f"No valid UUID found in '{file_uuid_or_url}'"}

    base_url, api_key, _ = get_chibisafe_config()
    if not base_url or not api_key:
        return {"success": False, "error": "Chibisafe configuration missing"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            headers = {"x-api-key": api_key}
            del_resp = await client.delete(f"{base_url}/api/file/{file_uuid}", headers=headers)

            if del_resp.status_code in (200, 204):
                logger.info(f"Deleted file {file_uuid} from Chibisafe server successfully")
                return {"success": True, "uuid": file_uuid, "message": "File deleted from remote server"}
            elif del_resp.status_code == 404:
                # File already deleted or not found
                logger.info(f"File {file_uuid} was already absent on Chibisafe server (404)")
                return {"success": True, "uuid": file_uuid, "message": "File already removed on remote server"}
            else:
                logger.warning(f"Chibisafe delete returned status {del_resp.status_code}: {del_resp.text}")
                return {"success": False, "error": del_resp.text}
    except Exception as e:
        logger.error(f"Exception deleting file {file_uuid} from Chibisafe: {e}")
        return {"success": False, "error": str(e)}

async def get_chibisafe_status() -> Dict[str, Any]:
    """
    Checks connection to Chibisafe server and returns version and album info.
    """
    base_url, api_key, album_uuid = get_chibisafe_config()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            v_res = await client.get(f"{base_url}/api/version", headers={"x-api-key": api_key})
            version = v_res.json().get("version") if v_res.status_code == 200 else "unknown"

            albums_res = await client.get(f"{base_url}/api/albums", headers={"x-api-key": api_key})
            album_count = 0
            album_name = None
            if albums_res.status_code == 200:
                data = albums_res.json()
                albums = data.get("albums", [])
                album_count = len(albums)
                target = next((a for a in albums if a.get("uuid") == album_uuid), None)
                if target:
                    album_name = target.get("name")

            return {
                "online": True,
                "base_url": base_url,
                "version": version,
                "album_uuid": album_uuid,
                "album_name": album_name,
                "total_albums": album_count,
            }
    except Exception as e:
        return {
            "online": False,
            "base_url": base_url,
            "error": str(e),
        }
