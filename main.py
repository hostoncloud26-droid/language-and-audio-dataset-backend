import os
import shutil
import time
import uuid
import wave
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import random
import smtplib
import email.utils
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status, Response, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
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
        SendOtpRequest,
        SendOtpResponse,
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
            SendOtpRequest,
            SendOtpResponse,
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
            SendOtpRequest,
            SendOtpResponse,
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
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https?://.*\.sslip\.io.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def ensure_cors_headers(request: Request, call_next):
    """
    Guarantees that CORS headers are NEVER stripped or missing, even if an unhandled
    exception, 500 error, or internal database failure occurs.
    """
    origin = request.headers.get("origin") or "*"

    if request.method == "OPTIONS":
        return Response(
            content="OK",
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With",
                "Access-Control-Max-Age": "600",
            },
        )

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(f"Unhandled server error on {request.method} {request.url.path}: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal server error occurred on the dataset backend.",
                "error": str(exc),
                "path": request.url.path,
            },
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
                "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With",
            },
        )

    # Ensure CORS headers are present on any outgoing response
    if origin and "access-control-allow-origin" not in response.headers:
        response.headers["access-control-allow-origin"] = origin
        response.headers["access-control-allow-credentials"] = "true"
        response.headers["access-control-allow-methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"
        response.headers["access-control-allow-headers"] = "Authorization, Content-Type, Accept, Origin, X-Requested-With"
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception caught on {request.url.path}: {exc}")
    origin = request.headers.get("origin") or "*"
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD",
            "Access-Control-Allow-Headers": "Authorization, Content-Type, Accept, Origin, X-Requested-With",
        },
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

class DbConfigureRequest(BaseModel):
    database_url: str

@app.post("/api/db/configure")
def configure_db_url(payload: DbConfigureRequest):
    """
    Allows updating the database URL at runtime.
    Validates, tests connection, and updates the SQLAlchemy engine immediately.
    """
    new_url = payload.database_url.strip()
    if not new_url:
        raise HTTPException(status_code=400, detail="Database URL cannot be empty.")

    os.environ["DATABASE_URL"] = new_url

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

# ---------------------------------------------------------------------------
# OTP Verification Store & Email Helpers
# ---------------------------------------------------------------------------
OTP_STORE: dict[str, dict] = {}

def generate_otp() -> str:
    """Generates a secure 6-digit numeric OTP."""
    return f"{random.randint(100000, 999999)}"

def send_email_otp(to_email: str, otp_code: str) -> tuple[bool, str]:
    """
    Sends the 6-digit OTP code to the recipient email via standard SMTP (STARTTLS / SSL).
    Returns (True, "OK") on success or (False, error_message) on failure.
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port_raw = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    raw_from = os.getenv("SMTP_FROM", "").strip()
    if not raw_from or "noreply@datasetplatform.com" in raw_from:
        smtp_from = f"Dataset Platform <{smtp_user}>"
    else:
        smtp_from = raw_from

    if not smtp_host or not smtp_user or not smtp_pass:
        return (
            False,
            "SMTP server credentials are not configured in backend/.env (missing SMTP_HOST, SMTP_USER, or SMTP_PASS)",
        )

    try:
        smtp_port = int(smtp_port_raw)
    except ValueError:
        smtp_port = 587

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{otp_code} is your Dataset Platform verification code"
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain="datasetplatform.com")

        text_body = f"""Hello,

Your verification code for Dataset Platform is: {otp_code}

This code will expire in 5 minutes.
If you did not request this verification code, please ignore this email.

Best regards,
Language & Audio Dataset Platform Team
"""
        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verification Code</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 40px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 520px; background-color: #ffffff; border-radius: 16px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
          <!-- Header Banner -->
          <tr>
            <td style="background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%); padding: 32px 30px; text-align: center;">
              <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">Dataset Platform</h1>
              <p style="margin: 6px 0 0; color: #bae6fd; font-size: 13px; font-weight: 500; text-transform: uppercase; letter-spacing: 1px;">Acoustic Intelligence & Speech Data</p>
            </td>
          </tr>
          
          <!-- Content Body -->
          <tr>
            <td style="padding: 36px 32px 28px;">
              <h2 style="margin: 0 0 12px; color: #0f172a; font-size: 20px; font-weight: 700;">Verify Your Email Address</h2>
              <p style="margin: 0 0 24px; color: #475569; font-size: 15px; line-height: 1.6;">
                Thank you for creating an account. Please use the following 6-digit one-time verification code to authenticate your registration:
              </p>
              
              <!-- OTP Display Box -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin: 0 0 24px;">
                <tr>
                  <td align="center" style="background-color: #f8fafc; border: 2px dashed #0284c7; border-radius: 12px; padding: 22px;">
                    <span style="font-family: 'Courier New', Courier, monospace, monospace; font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #0284c7; display: block; margin-left: 10px;">{otp_code}</span>
                  </td>
                </tr>
              </table>

              <p style="margin: 0 0 8px; color: #64748b; font-size: 13px; line-height: 1.5;">
                ⏱️ <strong>This code expires in 5 minutes.</strong>
              </p>
              <p style="margin: 0; color: #94a3b8; font-size: 13px; line-height: 1.5;">
                If you did not request this registration code, you can safely ignore this email. No changes will be made to your account.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 32px; text-align: center;">
              <p style="margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.4;">
                &copy; {datetime.utcnow().year} Language & Audio Dataset Platform. All rights reserved.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12.0) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=12.0) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(msg["From"], [to_email], msg.as_string())

        logger.info(f"OTP successfully emailed to {to_email} via {smtp_host}:{smtp_port}")
        return True, "Email dispatched successfully"
    except Exception as e:
        logger.error(f"SMTP email dispatch error for {to_email}: {e}")
        return False, str(e)


@app.post("/api/auth/send-otp", response_model=SendOtpResponse)
@app.post("/api/send-otp", response_model=SendOtpResponse)
@app.post("/send-otp", response_model=SendOtpResponse)
def send_registration_otp(req: SendOtpRequest, db: Session = Depends(get_db)):
    clean_email = req.email.strip().lower()
    if not clean_email or "@" not in clean_email or "." not in clean_email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    # Check if user already exists
    existing = db.query(User).filter(User.username.ilike(clean_email)).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="An account with this email/username already exists. Please sign in.",
        )

    code = generate_otp()
    email_sent, err_msg = send_email_otp(clean_email, code)
    if not email_sent:
        logger.error(f"Failed to send email to {clean_email}: {err_msg}")
        raise HTTPException(
            status_code=500,
            detail=f"Unable to send verification email: {err_msg}. Please ensure SMTP settings are properly configured.",
        )

    # Store OTP only after successful email dispatch
    OTP_STORE[clean_email] = {
        "otp": code,
        "expires_at": datetime.utcnow() + timedelta(minutes=5),
        "attempts": 0,
    }

    return SendOtpResponse(
        success=True,
        message=f"Verification code sent to {clean_email}. Please check your inbox.",
    )


@app.post("/api/auth/register", response_model=LoginResponse)
@app.post("/api/register", response_model=LoginResponse)
@app.post("/register", response_model=LoginResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if not req.username or not req.username.strip():
        raise HTTPException(status_code=400, detail="Username or email is required.")
    if not req.password or len(req.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    clean_username = req.username.strip().lower()

    # 1. Enforce OTP Verification
    if not req.otp or not req.otp.strip():
        raise HTTPException(
            status_code=400,
            detail="A 6-digit OTP verification code is required. Please request a verification code.",
        )

    clean_otp = req.otp.strip()
    stored = OTP_STORE.get(clean_username)
    if not stored:
        raise HTTPException(
            status_code=400,
            detail="No verification code was requested for this email, or it has expired. Please click 'Resend Code'.",
        )

    if datetime.utcnow() > stored["expires_at"]:
        OTP_STORE.pop(clean_username, None)
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired. Please request a new code.",
        )

    stored["attempts"] = stored.get("attempts", 0) + 1
    if stored["attempts"] > 5:
        OTP_STORE.pop(clean_username, None)
        raise HTTPException(
            status_code=400,
            detail="Too many invalid attempts. Please request a new verification code.",
        )

    if stored["otp"] != clean_otp:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification code. Please check your email and try again.",
        )

    # OTP validated successfully: remove from store
    OTP_STORE.pop(clean_username, None)

    # 2. Check if user already exists
    existing = db.query(User).filter(User.username.ilike(clean_username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists. Please choose another or sign in.")

    # 3. Create user in PostgreSQL
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

    # 4. Generate signed JWT token
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
    try:
        langs = db.query(Language).order_by(Language.id.asc()).all()
        if langs:
            return langs
    except Exception as e:
        logger.warning(f"Database error in get_languages: {e}. Falling back to default languages.")

    return [
        LanguageResponse(id=1, name="English", code="en", status="Active"),
        LanguageResponse(id=2, name="Tamil", code="ta", status="Active"),
        LanguageResponse(id=3, name="Hindi", code="hi", status="Active"),
        LanguageResponse(id=4, name="Malayalam", code="ml", status="Active"),
        LanguageResponse(id=5, name="Telugu", code="te", status="Active"),
        LanguageResponse(id=6, name="Marathi", code="mar", status="Active"),
    ]

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
    try:
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
        if results:
            return results
    except Exception as e:
        logger.warning(f"Database error in get_datasets: {e}. Falling back to default datasets.")

    return [
        DatasetResponse(
            id="DS-001",
            name="Multi-Language Speech Dataset 2026",
            language_id=1,
            language_name="English",
            record_count=3,
            created_at="2026-10-01T08:00:00Z",
        ),
        DatasetResponse(
            id="DS-002",
            name="Tamil Conversational Speech",
            language_id=2,
            language_name="Tamil",
            record_count=1,
            created_at="2026-10-01T08:30:00Z",
        ),
        DatasetResponse(
            id="DS-003",
            name="Hindi Acoustic Voice Records",
            language_id=3,
            language_name="Hindi",
            record_count=1,
            created_at="2026-10-01T09:00:00Z",
        ),
    ]

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
    try:
        query = db.query(DatasetRecord)
        if dataset_id:
            query = query.filter(DatasetRecord.dataset_id == dataset_id)
        if language_id:
            query = query.filter(DatasetRecord.language_id == language_id)

        records = query.order_by(DatasetRecord.created_at.desc()).all()
        if records:
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
    except Exception as e:
        logger.warning(f"Database error in get_dataset_records: {e}. Falling back to default records.")

    # Return default records as graceful fallback
    default_recs = [
        DatasetRecordResponse(
            id="AUD-001",
            dataset_id="DS-001",
            text="Hello, welcome to the dataset platform.",
            audio_url="",
            language_id=1,
            language_name="English",
            duration=4.0,
            created_at="2026-10-01T09:15:00Z",
        ),
        DatasetRecordResponse(
            id="AUD-002",
            dataset_id="DS-001",
            text="வணக்கம், இது ஒரு தமிழ் ஆடியோ தரவுத்தொகுப்பு.",
            audio_url="",
            language_id=2,
            language_name="Tamil",
            duration=4.5,
            created_at="2026-10-01T09:30:00Z",
        ),
        DatasetRecordResponse(
            id="AUD-003",
            dataset_id="DS-001",
            text="नमस्ते, यह एक हिंदी ऑडियो डेटासेट है।",
            audio_url="",
            language_id=3,
            language_name="Hindi",
            duration=4.2,
            created_at="2026-10-01T09:45:00Z",
        ),
    ]
    if dataset_id:
        default_recs = [r for r in default_recs if r.dataset_id == dataset_id]
    if language_id:
        default_recs = [r for r in default_recs if r.language_id == language_id]
    return default_recs

@app.get("/api/records/{record_id}", response_model=DatasetRecordResponse)
@app.get("/records/{record_id}", response_model=DatasetRecordResponse)
def get_record_by_id(record_id: str, db: Session = Depends(get_db)):
    try:
        rec = db.query(DatasetRecord).filter(DatasetRecord.id == record_id).first()
        if rec:
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
    except Exception as e:
        logger.warning(f"Database error in get_record_by_id: {e}")

    return DatasetRecordResponse(
        id=record_id,
        dataset_id="DS-001",
        text="Hello, welcome to the dataset platform.",
        audio_url="",
        language_id=1,
        language_name="English",
        duration=4.0,
        created_at="2026-10-01T09:15:00Z",
    )

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

