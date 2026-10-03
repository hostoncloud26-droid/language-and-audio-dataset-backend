import sys
import os
import uvicorn
from pathlib import Path

# Fix Windows cp1252 encoding for stdout/stderr
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure backend directory and its parent are in sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
root_dir = backend_dir.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Detect whether we should import from 'backend' package or direct module
try:
    from backend.config import PORT, HOST, DATABASE_URL
    from backend.database import check_db_connection
    app_target = "backend.main:app"
except ImportError:
    from config import PORT, HOST, DATABASE_URL
    from database import check_db_connection
    app_target = "main:app"

# If current working directory is inside the backend directory, "main:app" is always valid
if Path.cwd().resolve() == backend_dir:
    app_target = "main:app"

def main():
    print("=" * 60)
    print("[*] Starting Language & Audio Dataset Platform - FastAPI Server")
    print(f"[-] Host: http://{HOST}:{PORT}")
    print(f"[-] Swagger Docs: http://localhost:{PORT}/docs")
    print(f"[-] ReDoc Docs:   http://localhost:{PORT}/redoc")
    print(f"[-] Health API:   http://localhost:{PORT}/api/health")
    print(f"[-] DB Status:    http://localhost:{PORT}/api/db/status")

    db_status = check_db_connection()
    if db_status["connected"]:
        print(f"[OK] PostgreSQL Database: Connected ({db_status.get('database')})")
        print(f"     Connection: {db_status.get('url_masked')}")
    else:
        print(f"[WARN] PostgreSQL Database: Not connected yet.")
        print(f"       Reason: {db_status.get('error')}")
        print("       Configure your custom DATABASE_URL in the .env file.")
    print("=" * 60)

    uvicorn.run(app_target, host=HOST, port=PORT, reload=False)

if __name__ == "__main__":
    main()
