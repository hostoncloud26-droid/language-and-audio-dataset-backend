import os
import shutil
import time
import uuid
import wave
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, text
from sqlalchemy.orm import Session
import httpx

try:
    from .config import (
        PORT,
        HOST,
        DEBUG,
        CORS_ORIGINS,
        MEDIA_DIR,
        UPLOADS_DIR,
    )
    from .database import get_db, init_db, check_db_connection, Base, get_engine
    from .models import Language, Dataset, DatasetRecord, User
    from .schemas import (
        LoginRequest,
        RegisterRequest,
        LoginResponse,
        UserResponse,
        LanguageResponse,
        LanguageCreate,
        LanguageUpdate,
        DatasetResponse,
        DatasetCreate,
        DatasetUpdate,
        DatasetDetailResponse,
        DatasetRecordResponse,
        DatasetRecordCreate,
        DatasetRecordUpdate,
        AudioUploadResponse,
        AudioGenerateRequest,
        AudioGenerateResponse,
        DbStatusResponse,
        SuccessResponse,
    )
    from .security import (
        hash_password,
        verify_password,
        create_access_token,
        get_current_user_optional,
    )
    from .audio_generator import generate_wav_file
    from .chibisafe_service import (
        upload_audio_to_chibisafe,
        delete_file_from_chibisafe,
        get_chibisafe_status,
        extract_chibisafe_uuid,
        get_chibisafe_config,
    )
    from .omnivoice_service import (
        synthesize_and_upload_audio,
        check_omnivoice_health,
        get_omnivoice_base_url,
    )
except (ImportError, ValueError):
    try:
        from backend.config import (
            PORT,
            HOST,
            DEBUG,
            CORS_ORIGINS,
            MEDIA_DIR,
            UPLOADS_DIR,
        )
        from backend.database import get_db, init_db, check_db_connection, Base, get_engine
        from backend.models import Language, Dataset, DatasetRecord, User
        from backend.schemas import (
            LoginRequest,
            RegisterRequest,
            LoginResponse,
            UserResponse,
            LanguageResponse,
            LanguageCreate,
            LanguageUpdate,
            DatasetResponse,
            DatasetCreate,
            DatasetUpdate,
            DatasetDetailResponse,
            DatasetRecordResponse,
            DatasetRecordCreate,
            DatasetRecordUpdate,
            AudioUploadResponse,
            AudioGenerateRequest,
            AudioGenerateResponse,
            DbStatusResponse,
            SuccessResponse,
        )
        from backend.security import (
            hash_password,
            verify_password,
            create_access_token,
            get_current_user_optional,
        )
        from backend.audio_generator import generate_wav_file
        from backend.chibisafe_service import (
            upload_audio_to_chibisafe,
            delete_file_from_chibisafe,
            get_chibisafe_status,
            extract_chibisafe_uuid,
            get_chibisafe_config,
        )
        from backend.omnivoice_service import (
            synthesize_and_upload_audio,
            check_omnivoice_health,
            get_omnivoice_base_url,
        )
    except ImportError:
        from config import (
            PORT,
            HOST,
            DEBUG,
            CORS_ORIGINS,
            MEDIA_DIR,
            UPLOADS_DIR,
        )
        from database import get_db, init_db, check_db_connection, Base, get_engine
        from models import Language, Dataset, DatasetRecord, User
        from schemas import (
            LoginRequest,
            RegisterRequest,
            LoginResponse,
            UserResponse,
            LanguageResponse,
            LanguageCreate,
            LanguageUpdate,
            DatasetResponse,
            DatasetCreate,
            DatasetUpdate,
            DatasetDetailResponse,
            DatasetRecordResponse,
            DatasetRecordCreate,
            DatasetRecordUpdate,
            AudioUploadResponse,
            AudioGenerateRequest,
            AudioGenerateResponse,
            DbStatusResponse,
            SuccessResponse,
        )
        from security import (
            hash_password,
            verify_password,
            create_access_token,
            get_current_user_optional,
        )
        from audio_generator import generate_wav_file
        from chibisafe_service import (
            upload_audio_to_chibisafe,
            delete_file_from_chibisafe,
            get_chibisafe_status,
            extract_chibisafe_uuid,
            get_chibisafe_config,
        )
        from omnivoice_service import (
            synthesize_and_upload_audio,
            check_omnivoice_health,
            get_omnivoice_base_url,
        )


logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables and seed if database is available
    init_db()
    yield

app = FastAPI(
    title="Language & Audio Dataset Platform API",
    description="High-performance FastAPI server with PostgreSQL for language datasets and audio collection.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all during development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount media directory for static audio serving (/media/uploads/..., /media/generated/...)
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


# ---------------------------------------------------------------------------
# Health & Database Status
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health_check():
    db_status = check_db_connection()
    return {
        "status": "online",
        "timestamp": time.time(),
        "database": "connected" if db_status["connected"] else "disconnected",
        "database_info": db_status,
    }

@app.get("/api/db/status", response_model=DbStatusResponse)
def get_db_status():
    status_info = check_db_connection()
    counts = None
    if status_info["connected"]:
        try:
            eng = get_engine()
            with Session(eng) as session:
                counts = {
                    "languages": session.query(Language).count(),
                    "datasets": session.query(Dataset).count(),
                    "records": session.query(DatasetRecord).count(),
                    "users": session.query(User).count(),
                }
        except Exception:
            pass
    return DbStatusResponse(
        connected=status_info["connected"],
        database=status_info.get("database"),
        user=status_info.get("user"),
        version=status_info.get("version"),
        url_masked=status_info.get("url_masked"),
        error=status_info.get("error"),
        counts=counts,
    )

@app.post("/api/db/reconnect")
def reconnect_db():
    """Triggered to reinitialize database connection after .env changes."""
    success = init_db()
    status_info = check_db_connection()
    return {
        "success": success,
        "status": status_info,
    }


# ---------------------------------------------------------------------------
# Secure Authentication Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/login", response_model=LoginResponse)
@app.post("/api/auth/login", response_model=LoginResponse)
@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    if not req.username or not req.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required.",
        )

    clean_username = req.username.strip().lower()

    # Query user from PostgreSQL
    user = db.query(User).filter(User.username.ilike(clean_username)).first()

    if user:
        # Verify password using bcrypt
        if not verify_password(req.password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password.",
            )
    else:
        # Auto-provision user in PostgreSQL if first login with valid password
        display_name = clean_username.split("@")[0].capitalize()
        user = User(
            id=f"usr-{uuid.uuid4().hex[:6]}",
            username=clean_username,
            password=hash_password(req.password),
            name=display_name,
            role="Dataset Specialist",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Generate signed JWT token
    token_payload = {
        "sub": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
    }
    jwt_token = create_access_token(token_payload)

    return LoginResponse(
        token=jwt_token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            name=user.name,
            role=user.role,
        ),
    )

@app.post("/api/auth/register", response_model=LoginResponse)
@app.post("/api/register", response_model=LoginResponse)
@app.post("/register", response_model=LoginResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if not req.username or not req.username.strip():
        raise HTTPException(status_code=400, detail="Username is required.")
    if not req.password or len(req.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    clean_username = req.username.strip().lower()
    existing = db.query(User).filter(User.username.ilike(clean_username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists. Please choose another or sign in.")

    display_name = req.name.strip() if req.name and req.name.strip() else clean_username.split("@")[0].capitalize()
    new_user = User(
        id=f"usr-{uuid.uuid4().hex[:6]}",
        username=clean_username,
        password=hash_password(req.password.strip()),
        name=display_name,
        role=req.role or "Dataset Specialist",
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token_payload = {
        "sub": new_user.id,
        "username": new_user.username,
        "name": new_user.name,
        "role": new_user.role,
    }
    jwt_token = create_access_token(token_payload)

    return LoginResponse(
        token=jwt_token,
        user=UserResponse(
            id=new_user.id,
            username=new_user.username,
            name=new_user.name,
            role=new_user.role,
        ),
    )

@app.get("/api/auth/me")
@app.get("/api/me")
@app.get("/me")
def get_current_user(current_user: Optional[dict] = Depends(get_current_user_optional)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication token missing or invalid.")
    return current_user


# ---------------------------------------------------------------------------
# Languages Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/languages", response_model=List[LanguageResponse])
@app.get("/languages", response_model=List[LanguageResponse])
def get_languages(db: Session = Depends(get_db)):
    langs = db.query(Language).order_by(Language.id.asc()).all()
    return langs

@app.post("/api/languages", response_model=LanguageResponse)
@app.post("/languages", response_model=LanguageResponse)
def create_language(payload: LanguageCreate, db: Session = Depends(get_db)):
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Language name is required.")

    existing = db.query(Language).filter(Language.name.ilike(clean_name)).first()
    if existing:
        return existing

    max_id = db.query(func.max(Language.id)).scalar() or 0
    new_lang = Language(
        id=max_id + 1,
        name=clean_name,
        code=(payload.code.strip().lower() if payload.code and payload.code.strip() else clean_name[:3].lower()),
        status=payload.status or "Active",
    )
    db.add(new_lang)
    db.commit()
    db.refresh(new_lang)

    # Sync sequence
    try:
        db.execute(text("SELECT setval(pg_get_serial_sequence('languages', 'id'), COALESCE(max(id), 1)) FROM languages;"))
        db.commit()
    except Exception:
        pass

    return new_lang

@app.put("/api/languages/{language_id}", response_model=LanguageResponse)
@app.patch("/api/languages/{language_id}", response_model=LanguageResponse)
def update_language(language_id: int, payload: LanguageUpdate, db: Session = Depends(get_db)):
    lang = db.query(Language).filter(Language.id == language_id).first()
    if not lang:
        raise HTTPException(status_code=404, detail="Language not found.")

    if payload.name is not None and payload.name.strip():
        lang.name = payload.name.strip()
    if payload.code is not None:
        lang.code = payload.code.strip().lower()
    if payload.status is not None:
        lang.status = payload.status

    db.commit()
    db.refresh(lang)
    return lang

@app.delete("/api/languages/{language_id}", response_model=SuccessResponse)
@app.delete("/languages/{language_id}", response_model=SuccessResponse)
def delete_language(language_id: int, db: Session = Depends(get_db)):
    lang = db.query(Language).filter(Language.id == language_id).first()
    if not lang:
        raise HTTPException(status_code=404, detail="Language not found.")

    ds_count = db.query(Dataset).filter(Dataset.language_id == language_id).count()
    if ds_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete language '{lang.name}' because {ds_count} dataset(s) depend on it.",
        )

    db.delete(lang)
    db.commit()
    return SuccessResponse(success=True, message=f"Language '{lang.name}' deleted successfully.")


# ---------------------------------------------------------------------------
# Datasets Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/datasets", response_model=List[DatasetResponse])
@app.get("/datasets", response_model=List[DatasetResponse])
def get_datasets(db: Session = Depends(get_db)):
    datasets = db.query(Dataset).order_by(Dataset.created_at.desc()).all()
    results = []
    for d in datasets:
        rec_count = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == d.id).count()
        lang_name = d.language.name if d.language else "Unknown"
        results.append(
            DatasetResponse(
                id=d.id,
                name=d.name,
                language_id=d.language_id,
                language_name=lang_name,
                record_count=rec_count,
                created_at=d.created_at.isoformat() if d.created_at else "",
            )
        )
    return results

@app.post("/api/datasets", response_model=DatasetResponse)
@app.post("/datasets", response_model=DatasetResponse)
def create_dataset(payload: DatasetCreate, db: Session = Depends(get_db)):
    existing_ids = {d[0] for d in db.query(Dataset.id).all()}
    idx = len(existing_ids) + 1
    while f"DS-{idx:03d}" in existing_ids:
        idx += 1
    new_id = f"DS-{idx:03d}"
    
    new_ds = Dataset(
        id=new_id,
        name=payload.name,
        language_id=payload.language_id,
        description=payload.description or "",
        record_count=0,
    )
    db.add(new_ds)
    db.commit()
    db.refresh(new_ds)
    
    lang_name = new_ds.language.name if new_ds.language else "English"
    return DatasetResponse(
        id=new_ds.id,
        name=new_ds.name,
        language_id=new_ds.language_id,
        language_name=lang_name,
        record_count=0,
        created_at=new_ds.created_at.isoformat() if new_ds.created_at else "",
    )

@app.get("/api/datasets/{dataset_id}", response_model=DatasetDetailResponse)
@app.get("/datasets/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset_by_id(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        ds = db.query(Dataset).first()
        if not ds:
            raise HTTPException(status_code=404, detail="Dataset not found.")

    records = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == ds.id).order_by(DatasetRecord.created_at.desc()).all()
    lang_name = ds.language.name if ds.language else "English"

    formatted_records = [
        DatasetRecordResponse(
            id=r.id,
            dataset_id=r.dataset_id,
            text=r.text,
            audio_url=r.audio_url,
            language_id=r.language_id,
            language_name=r.language_name or (r.language.name if r.language else "English"),
            duration=r.duration,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in records
    ]

    return DatasetDetailResponse(
        dataset=DatasetResponse(
            id=ds.id,
            name=ds.name,
            language_id=ds.language_id,
            language_name=lang_name,
            record_count=len(formatted_records),
            created_at=ds.created_at.isoformat() if ds.created_at else "",
        ),
        records=formatted_records,
    )

@app.get("/api/datasets/{dataset_id}/records", response_model=List[DatasetRecordResponse])
@app.get("/datasets/{dataset_id}/records", response_model=List[DatasetRecordResponse])
@app.get("/api/records", response_model=List[DatasetRecordResponse])
def get_dataset_records(
    dataset_id: Optional[str] = None,
    language_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(DatasetRecord)
    if dataset_id:
        query = query.filter(DatasetRecord.dataset_id == dataset_id)
    if language_id:
        query = query.filter(DatasetRecord.language_id == language_id)

    records = query.order_by(DatasetRecord.created_at.desc()).all()
    return [
        DatasetRecordResponse(
            id=r.id,
            dataset_id=r.dataset_id,
            text=r.text,
            audio_url=r.audio_url,
            language_id=r.language_id,
            language_name=r.language_name or (r.language.name if r.language else "English"),
            duration=r.duration,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in records
    ]

# ---------------------------------------------------------------------------
# Approve and Save Record to Dataset (Section 11 & Section 17 of PDF)
# ---------------------------------------------------------------------------
@app.post("/api/datasets/{dataset_id}/records")
@app.post("/datasets/{dataset_id}/records")
@app.post("/api/records")
def save_record_to_dataset(
    payload: DatasetRecordCreate,
    dataset_id: Optional[str] = "DS-001",
    db: Session = Depends(get_db),
):
    target_ds_id = dataset_id or "DS-001"
    ds = db.query(Dataset).filter(Dataset.id == target_ds_id).first()
    if not ds:
        ds = db.query(Dataset).first()
        if ds:
            target_ds_id = ds.id
        else:
            raise HTTPException(status_code=404, detail="No active dataset found to save record.")

    existing_ids = {r[0] for r in db.query(DatasetRecord.id).all()}
    idx = len(existing_ids) + 1
    while f"AUD-{idx:03d}" in existing_ids:
        idx += 1
    new_record_id = f"AUD-{idx:03d}"

    lang_id_num = int(payload.language_id) if str(payload.language_id).isdigit() else 1
    lang_obj = db.query(Language).filter(Language.id == lang_id_num).first()
    lang_name = payload.language_name or (lang_obj.name if lang_obj else "English")

    new_record = DatasetRecord(
        id=new_record_id,
        dataset_id=target_ds_id,
        text=payload.text,
        audio_url=payload.audio_url,
        language_id=lang_id_num,
        language_name=lang_name,
        duration=payload.duration or 4.0,
    )
    db.add(new_record)
    
    if ds:
        ds.record_count = (ds.record_count or 0) + 1

    db.commit()
    db.refresh(new_record)

    return {
        "id": new_record.id,
        "success": True,
        "record": DatasetRecordResponse(
            id=new_record.id,
            dataset_id=new_record.dataset_id,
            text=new_record.text,
            audio_url=new_record.audio_url,
            language_id=new_record.language_id,
            language_name=new_record.language_name,
            duration=new_record.duration,
            created_at=new_record.created_at.isoformat() if new_record.created_at else "",
        ),
    }

@app.put("/api/datasets/{dataset_id}", response_model=DatasetResponse)
@app.patch("/api/datasets/{dataset_id}", response_model=DatasetResponse)
def update_dataset(dataset_id: str, payload: DatasetUpdate, db: Session = Depends(get_db)):
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    if payload.name is not None and payload.name.strip():
        ds.name = payload.name.strip()
    if payload.description is not None:
        ds.description = payload.description.strip()

    db.commit()
    db.refresh(ds)
    rec_count = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == ds.id).count()
    return DatasetResponse(
        id=ds.id,
        name=ds.name,
        language_id=ds.language_id,
        language_name=ds.language.name if ds.language else "Unknown",
        record_count=rec_count,
        created_at=ds.created_at.isoformat() if ds.created_at else "",
    )

@app.delete("/api/datasets/{dataset_id}", response_model=SuccessResponse)
@app.delete("/datasets/{dataset_id}", response_model=SuccessResponse)
async def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")

    # 1. Fetch all records in dataset to clean up files from remote Chibisafe server
    records = db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id).all()
    for rec in records:
        if rec.audio_url:
            try:
                await delete_file_from_chibisafe(rec.audio_url)
            except Exception as e:
                logger.warning(f"Error deleting file from server for record {rec.id}: {e}")

    # 2. Delete records from database
    db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id).delete()
    db.delete(ds)
    db.commit()
    return SuccessResponse(
        success=True,
        message=f"Dataset '{dataset_id}' and all associated server files deleted successfully."
    )

@app.put("/api/records/{record_id}", response_model=DatasetRecordResponse)
@app.patch("/api/records/{record_id}", response_model=DatasetRecordResponse)
async def update_record(record_id: str, payload: DatasetRecordUpdate, db: Session = Depends(get_db)):
    rec = db.query(DatasetRecord).filter(DatasetRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found.")

    if payload.text is not None:
        rec.text = payload.text.strip()
    if payload.language_id is not None:
        rec.language_id = int(payload.language_id) if str(payload.language_id).isdigit() else rec.language_id
    if payload.language_name is not None:
        rec.language_name = payload.language_name.strip()
    if payload.audio_url is not None and payload.audio_url.strip():
        new_url = payload.audio_url.strip()
        # If audio URL changed and old audio had a Chibisafe UUID, remove old file from server
        if rec.audio_url and rec.audio_url != new_url:
            try:
                await delete_file_from_chibisafe(rec.audio_url)
            except Exception as e:
                logger.warning(f"Could not delete replaced audio file: {e}")
        rec.audio_url = new_url

    db.commit()
    db.refresh(rec)

    return DatasetRecordResponse(
        id=rec.id,
        dataset_id=rec.dataset_id,
        text=rec.text,
        audio_url=rec.audio_url,
        language_id=rec.language_id,
        language_name=rec.language_name or (rec.language.name if rec.language else "English"),
        duration=rec.duration,
        created_at=rec.created_at.isoformat() if rec.created_at else "",
    )

@app.delete("/api/records/{record_id}", response_model=SuccessResponse)
@app.delete("/api/datasets/{dataset_id}/records/{record_id}", response_model=SuccessResponse)
async def delete_record(record_id: str, dataset_id: Optional[str] = None, db: Session = Depends(get_db)):
    rec = db.query(DatasetRecord).filter(DatasetRecord.id == record_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found.")

    target_ds_id = rec.dataset_id
    audio_url = rec.audio_url

    # 1. Trigger remote Chibisafe API to delete the audio file on the server
    if audio_url:
        try:
            del_result = await delete_file_from_chibisafe(audio_url)
            logger.info(f"Server file deletion for record {record_id}: {del_result}")
        except Exception as e:
            logger.warning(f"Error deleting file from server for record {record_id}: {e}")

    # 2. Delete record from PostgreSQL
    db.delete(rec)

    ds = db.query(Dataset).filter(Dataset.id == target_ds_id).first()
    if ds and ds.record_count and ds.record_count > 0:
        ds.record_count = max(0, ds.record_count - 1)

    db.commit()
    return SuccessResponse(
        success=True,
        message=f"Record '{record_id}' deleted successfully from database and remote server."
    )


# ---------------------------------------------------------------------------
# Audio Upload & Audio Generation (Section 8, 9, 10 of PDF)
# ---------------------------------------------------------------------------
@app.post("/api/upload", response_model=AudioUploadResponse)
@app.post("/api/audio/upload", response_model=AudioUploadResponse)
@app.post("/audio/upload", response_model=AudioUploadResponse)
async def upload_audio(
    file: UploadFile = File(...),
    language_id: Optional[str] = Form(None),
):
    ext = os.path.splitext(file.filename)[1].lower()
    allowed_exts = [".wav", ".mp3", ".m4a", ".ogg", ".webm", ".aac"]
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{ext}'. Allowed formats: WAV, MP3, M4A, OGG, WEBM.",
        )

    # Read file content into memory
    file_bytes = await file.read()

    unique_filename = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
    saved_file_path = UPLOADS_DIR / unique_filename

    # Save local copy as backup
    try:
        with open(saved_file_path, "wb") as buffer:
            buffer.write(file_bytes)
    except Exception as e:
        logger.warning(f"Failed to save local backup file: {e}")

    # Compute duration if WAV
    duration = 4.0
    if ext == ".wav":
        try:
            with wave.open(str(saved_file_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    duration = round(frames / float(rate), 2)
        except Exception:
            pass

    # Save to remote server (Chibisafe) via REST API
    chibi_res = await upload_audio_to_chibisafe(
        file_bytes=file_bytes,
        filename=file.filename or unique_filename,
        content_type=file.content_type,
    )

    file_uuid = None
    if chibi_res.get("success") and chibi_res.get("audio_url"):
        final_audio_url = chibi_res["audio_url"]
        file_uuid = chibi_res.get("uuid")
        logger.info(f"Audio file saved to remote server successfully: {final_audio_url}")
    else:
        final_audio_url = f"/media/uploads/{unique_filename}"
        logger.warning(f"Remote upload fallback to local URL: {chibi_res.get('error')}")

    return AudioUploadResponse(
        audio_url=final_audio_url,
        filename=file.filename or unique_filename,
        duration=duration,
        uuid=file_uuid,
    )

@app.get("/api/audio/remote/{file_uuid}")
async def stream_remote_audio(file_uuid: str):
    """
    Direct proxy/streaming route for audio files stored on Chibisafe server.
    """
    base_url, _, _ = get_chibisafe_config()
    remote_url = f"{base_url}/api/file/{file_uuid}/download"
    try:
        client = httpx.AsyncClient(timeout=20.0)
        req = client.build_request("GET", remote_url)
        resp = await client.send(req, stream=True)
        if resp.status_code != 200:
            await resp.aclose()
            await client.aclose()
            raise HTTPException(status_code=resp.status_code, detail="Remote audio file not found.")

        async def stream_generator():
            try:
                async for chunk in resp.aiter_bytes():
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        headers = {
            "Content-Type": resp.headers.get("content-type", "audio/wav"),
            "Content-Disposition": resp.headers.get("content-disposition", f'inline; filename="{file_uuid}.wav"'),
            "Access-Control-Allow-Origin": "*",
        }
        return StreamingResponse(stream_generator(), status_code=200, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stream from remote server: {e}")

@app.post("/api/generate", response_model=AudioGenerateResponse)
@app.post("/api/audio/generate", response_model=AudioGenerateResponse)
@app.post("/audio/generate", response_model=AudioGenerateResponse)
async def generate_audio(payload: AudioGenerateRequest):
    """
    Generates speech via OmniVoice API (or resilient synthesizer fallback)
    and uploads the generated audio clip directly to the Chibisafe remote server.
    """
    if not payload.text or not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text is required for audio generation.")

    lang_id = int(payload.language_id) if str(payload.language_id).isdigit() else 1
    lang_name = payload.language_name or "English"

    result = await synthesize_and_upload_audio(
        text=payload.text,
        language_id=lang_id,
        language_name=lang_name,
        lang_code=payload.lang_code,
        ref_audio=payload.ref_audio or "reference.mp3",
        upload_to_server=True,
    )

    return AudioGenerateResponse(
        audio_url=result["audio_url"],
        filename=result["filename"],
        duration=result["duration"],
        engine=result.get("engine"),
        lang_code=result.get("lang_code"),
    )

# ---------------------------------------------------------------------------
# Remote Services Status & Health Check Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/system-info")
@app.get("/api/audio/omnivoice/status")
@app.get("/api/omnivoice/status")
@app.get("/api/omnivoice/health")
async def get_omnivoice_status():
    """
    OmniVoice health check endpoint (mirrors curl -i $BASE/api/system-info).
    """
    status_info = await check_omnivoice_health(timeout=3.0)
    return status_info

@app.get("/api/chibisafe/status")
async def get_remote_chibisafe_status():
    """
    Chibisafe remote file server health and album status.
    """
    return await get_chibisafe_status()

@app.get("/api/external/status")
async def get_all_external_status():
    """
    Aggregated health check of both integrated external services:
    Chibisafe (file upload/storage) and OmniVoice (voice generation).
    """
    chibi = await get_chibisafe_status()
    omni = await check_omnivoice_health(timeout=3.0)
    return {
        "chibisafe": chibi,
        "omnivoice": omni,
    }

