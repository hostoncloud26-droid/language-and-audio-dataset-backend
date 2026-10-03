import logging
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
try:
    from .config import get_database_url
except (ImportError, ValueError):
    try:
        from backend.config import get_database_url
    except ImportError:
        from config import get_database_url

logger = logging.getLogger("uvicorn.error")

Base = declarative_base()

_engine = None
_session_maker = None
_current_url = ""

def get_engine():
    global _engine, _session_maker, _current_url
    latest_url = get_database_url()

    # Reconnect if engine not created or DATABASE_URL changed
    if latest_url and (_engine is None or latest_url != _current_url):
        try:
            connect_args = {}
            if "postgresql" in latest_url:
                connect_args = {"connect_timeout": 10}

            _engine = create_engine(
                latest_url,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                pool_recycle=300,
                connect_args=connect_args,
            )
            _session_maker = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
            _current_url = latest_url
            logger.info("✅ PostgreSQL SQLAlchemy engine initialized for database connection.")
        except Exception as e:
            logger.error(f"❌ Failed to create SQLAlchemy engine: {e}")
            _engine = None
            _session_maker = None

    return _engine

def get_session_maker():
    get_engine()
    return _session_maker

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    """
    sm = get_session_maker()
    if sm is None:
        raise RuntimeError(
            "Database engine is not configured. Please ensure DATABASE_URL is set in your .env file."
        )
    db = sm()
    try:
        yield db
    finally:
        db.close()

def check_db_connection() -> dict:
    """
    Test the PostgreSQL database connection and return status information.
    """
    url = get_database_url()
    if not url:
        return {
            "connected": False,
            "error": "DATABASE_URL is not set in .env. Please configure your custom PostgreSQL connection string.",
            "url_masked": None,
        }

    # Mask password for display
    masked_url = url
    if "@" in masked_url and "://" in masked_url:
        prefix, rest = masked_url.split("://", 1)
        creds, host_part = rest.split("@", 1)
        user = creds.split(":")[0] if ":" in creds else creds
        masked_url = f"{prefix}://{user}:*****@{host_part}"

    eng = get_engine()
    if eng is None:
        return {
            "connected": False,
            "error": "Failed to create SQLAlchemy engine for the provided DATABASE_URL.",
            "url_masked": masked_url,
        }

    try:
        with eng.connect() as conn:
            result = conn.execute(text("SELECT version(), current_database(), current_user;")).fetchone()
            return {
                "connected": True,
                "version": result[0] if result else "Unknown",
                "database": result[1] if result else "Unknown",
                "user": result[2] if result else "Unknown",
                "url_masked": masked_url,
            }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "url_masked": masked_url,
        }

def init_db():
    """
    Create tables if they don't exist and run initial seeding.
    """
    status = check_db_connection()
    if not status["connected"]:
        logger.warning(
            f"⚠️ Database not yet connected: {status['error']}\n"
            f"   The server is running. You can update your custom DATABASE_URL in .env at any time."
        )
        return False

    try:
        eng = get_engine()
        # Import models so Base.metadata knows about all tables
        try:
            from . import models  # noqa
        except (ImportError, ValueError):
            try:
                import backend.models as models  # noqa
            except ImportError:
                import models  # noqa

        Base.metadata.create_all(bind=eng)
        logger.info("✅ Database tables verified and created successfully.")

        # Seed default initial data if tables are empty
        try:
            from .seed import seed_initial_data
        except (ImportError, ValueError):
            try:
                from backend.seed import seed_initial_data
            except ImportError:
                from seed import seed_initial_data
        seed_initial_data()
        return True
    except Exception as e:
        logger.error(f"❌ Error during database initialization / table creation: {e}")
        return False
