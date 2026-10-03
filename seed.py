import logging
from datetime import datetime
try:
    from .database import get_session_maker
    from .models import Language, Dataset, DatasetRecord, User
    from .audio_generator import generate_wav_file
    from .security import hash_password
except (ImportError, ValueError):
    try:
        from backend.database import get_session_maker
        from backend.models import Language, Dataset, DatasetRecord, User
        from backend.audio_generator import generate_wav_file
        from backend.security import hash_password
    except ImportError:
        from database import get_session_maker
        from models import Language, Dataset, DatasetRecord, User
        from audio_generator import generate_wav_file
        from security import hash_password

logger = logging.getLogger("uvicorn.error")

def seed_initial_data():
    """
    Seeds initial default languages, datasets, and secure users into PostgreSQL if tables are empty.
    """
    sm = get_session_maker()
    if sm is None:
        return

    db = sm()
    try:
        # 1. Seed Languages
        existing_langs = db.query(Language).count()
        if existing_langs == 0:
            logger.info("🌱 Seeding initial languages into PostgreSQL...")
            languages_to_seed = [
                Language(id=1, name="English", code="en", status="Active"),
                Language(id=2, name="Tamil", code="ta", status="Active"),
                Language(id=3, name="Hindi", code="hi", status="Active"),
                Language(id=4, name="Malayalam", code="ml", status="Active"),
                Language(id=5, name="Telugu", code="te", status="Active"),
            ]
            db.add_all(languages_to_seed)
            db.commit()

        # Synchronize PostgreSQL sequence for languages.id
        try:
            from sqlalchemy import text
            db.execute(text("SELECT setval(pg_get_serial_sequence('languages', 'id'), COALESCE(max(id), 1)) FROM languages;"))
            db.commit()
        except Exception:
            pass

        # 2. Seed Default Secure Users with Bcrypt Hashed Passwords
        default_users = [
            {
                "id": "usr-janu-01",
                "username": "janu09@gmail.com",
                "password": "password123",
                "name": "Janu S",
                "role": "Dataset Specialist",
            },
            {
                "id": "usr-admin-01",
                "username": "admin",
                "password": "admin123",
                "name": "System Administrator",
                "role": "Administrator",
            },
            {
                "id": "usr-specialist-01",
                "username": "specialist",
                "password": "DatasetUser@2026!",
                "name": "Dataset Specialist",
                "role": "Dataset Specialist",
            },
            {
                "id": "usr-demo-01",
                "username": "demo",
                "password": "demo123",
                "name": "Demo Specialist",
                "role": "Dataset Specialist",
            },
        ]

        for u in default_users:
            existing_u = db.query(User).filter(User.username.ilike(u["username"])).first()
            if not existing_u:
                new_u = User(
                    id=u["id"],
                    username=u["username"].lower(),
                    password=hash_password(u["password"]),
                    name=u["name"],
                    role=u["role"],
                )
                db.add(new_u)
        db.commit()

        # 3. Seed Datasets
        if db.query(Dataset).count() == 0:
            logger.info("🌱 Seeding initial datasets into PostgreSQL...")
            datasets_to_seed = [
                Dataset(
                    id="DS-001",
                    name="Multi-Language Speech Dataset 2026",
                    language_id=1,
                    description="Standard benchmark speech corpus across English, Tamil, and Hindi utterances.",
                    record_count=3,
                    created_at=datetime.utcnow(),
                ),
                Dataset(
                    id="DS-002",
                    name="Tamil Conversational Speech",
                    language_id=2,
                    description="Colloquial conversational audio transcripts collected for Tamil speech recognition.",
                    record_count=0,
                    created_at=datetime.utcnow(),
                ),
                Dataset(
                    id="DS-003",
                    name="Hindi Acoustic Voice Records",
                    language_id=3,
                    description="Acoustic voice recordings and phonetic sets for Hindi voice models.",
                    record_count=0,
                    created_at=datetime.utcnow(),
                ),
            ]
            db.add_all(datasets_to_seed)
            db.commit()

        # 4. Seed Initial Audio Records for DS-001
        if db.query(DatasetRecord).count() == 0:
            logger.info("🌱 Generating and seeding initial audio records for DS-001...")
            
            # Generate real WAV files for initial items
            rec1_audio = generate_wav_file("Hello, welcome to the dataset platform.", 1, "English")
            rec2_audio = generate_wav_file("வணக்கம், இது ஒரு தமிழ் ஆடியோ தரவுத்தொகுப்பு.", 2, "Tamil")
            rec3_audio = generate_wav_file("नमस्ते, यह एक हिंदी ऑडियो डेटासेट है।", 3, "Hindi")

            records_to_seed = [
                DatasetRecord(
                    id="AUD-001",
                    dataset_id="DS-001",
                    text="Hello, welcome to the dataset platform.",
                    audio_url=rec1_audio["audio_url"],
                    language_id=1,
                    language_name="English",
                    duration=rec1_audio["duration"],
                    created_at=datetime.utcnow(),
                ),
                DatasetRecord(
                    id="AUD-002",
                    dataset_id="DS-001",
                    text="வணக்கம், இது ஒரு தமிழ் ஆடியோ தரவுத்தொகுப்பு.",
                    audio_url=rec2_audio["audio_url"],
                    language_id=2,
                    language_name="Tamil",
                    duration=rec2_audio["duration"],
                    created_at=datetime.utcnow(),
                ),
                DatasetRecord(
                    id="AUD-003",
                    dataset_id="DS-001",
                    text="नमस्ते, यह एक हिंदी ऑडियो डेटासेट है।",
                    audio_url=rec3_audio["audio_url"],
                    language_id=3,
                    language_name="Hindi",
                    duration=rec3_audio["duration"],
                    created_at=datetime.utcnow(),
                ),
            ]
            db.add_all(records_to_seed)
            db.commit()

        logger.info("✅ Database seed check completed successfully.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()
