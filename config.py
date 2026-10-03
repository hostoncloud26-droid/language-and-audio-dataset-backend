import os
from pathlib import Path
from dotenv import load_dotenv

# Base backend directory
BASE_DIR = Path(__file__).resolve().parent

# Check for .env in current backend dir or parent project dir
env_path_backend = BASE_DIR / ".env"
env_path_root = BASE_DIR.parent / ".env"

def reload_env():
    if env_path_backend.exists():
        load_dotenv(dotenv_path=env_path_backend, override=True)
    elif env_path_root.exists():
        load_dotenv(dotenv_path=env_path_root, override=True)
    else:
        load_dotenv(override=True)

# Initial load
reload_env()

def get_database_url() -> str:
    """
    Returns the current configured PostgreSQL connection string from the environment.
    Automatically normalizes dialect prefix and ensures database name is present.
    """
    reload_env()
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        return ""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    # If URL lacks a database path (e.g. postgresql://user:pass@host:port), append /postgres
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds_host = rest.split("@", 1)[1]
            if "?" in creds_host:
                host_part, query_part = creds_host.split("?", 1)
                if "/" not in host_part or host_part.endswith("/"):
                    host_clean = host_part.rstrip("/")
                    url = f"{scheme}://{rest.split('@', 1)[0]}@{host_clean}/postgres?{query_part}"
            else:
                if "/" not in creds_host or creds_host.endswith("/"):
                    url = f"{url.rstrip('/')}/postgres"

    return url

DATABASE_URL = get_database_url()

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("FASTAPI_PORT", os.getenv("PORT", "8000")))
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")

# JWT Settings
JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "vdf-dataset-platform-super-secure-jwt-key-2026-xyz-32bytes!"
)
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

# CORS
cors_env = os.getenv("CORS_ORIGINS", "")
if cors_env:
    CORS_ORIGINS = [origin.strip() for origin in cors_env.split(",") if origin.strip()]
else:
    CORS_ORIGINS = [
        "http://syqmo5sq5bozpvjfjjz3dxws.72.61.239.30.sslip.io",
        "https://syqmo5sq5bozpvjfjjz3dxws.72.61.239.30.sslip.io",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8000",
    ]

# Media directories for uploaded and generated audio
MEDIA_DIR = BASE_DIR / "media"
UPLOADS_DIR = MEDIA_DIR / "uploads"
GENERATED_DIR = MEDIA_DIR / "generated"

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

# Remote Chibisafe File Server Configuration
CHIBISAFE_URL = os.getenv(
    "CHIBISAFE_URL",
    "http://chibisafe-js70kfifmck6m9b4lzbe5hko.72.61.239.30.sslip.io"
).strip().rstrip("/")
CHIBISAFE_API_KEY = os.getenv(
    "CHIBISAFE_API_KEY",
    "QxDWe5hxUn5RtMp6cUFmqrNYZZDJQovV0p7I4KHM0mEzysVGS9vy4S4n8SpEUA6x"
).strip()
CHIBISAFE_ALBUM_UUID = os.getenv(
    "CHIBISAFE_ALBUM_UUID",
    "63219c42-774f-4eae-8448-7e75d446a63a"
).strip()

# Remote OmniVoice Voice Generation Server Configuration
OMNIVOICE_URL = os.getenv(
    "OMNIVOICE_URL",
    "http://47.29.133.221:32149"
).strip().rstrip("/")

