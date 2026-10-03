from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship

try:
    from .database import Base
except (ImportError, ValueError):
    try:
        from backend.database import Base
    except ImportError:
        from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True, index=True)
    username = Column(String(128), unique=True, index=True, nullable=False)
    password = Column(String(256), nullable=False)
    name = Column(String(128), nullable=False)
    role = Column(String(64), default="Dataset Specialist")
    created_at = Column(DateTime, default=datetime.utcnow)

class Language(Base):
    __tablename__ = "languages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(128), unique=True, nullable=False)
    code = Column(String(32), nullable=True)
    status = Column(String(32), default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    datasets = relationship("Dataset", back_populates="language", cascade="all, delete-orphan")
    records = relationship("DatasetRecord", back_populates="language")

class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(256), nullable=False)
    language_id = Column(Integer, ForeignKey("languages.id"), nullable=False)
    description = Column(Text, nullable=True)
    record_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    language = relationship("Language", back_populates="datasets")
    records = relationship("DatasetRecord", back_populates="dataset", cascade="all, delete-orphan")

class DatasetRecord(Base):
    __tablename__ = "dataset_records"

    id = Column(String(64), primary_key=True, index=True)
    dataset_id = Column(String(64), ForeignKey("datasets.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    audio_url = Column(String(512), nullable=False)
    language_id = Column(Integer, ForeignKey("languages.id"), nullable=False, index=True)
    language_name = Column(String(128), nullable=True)
    duration = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    dataset = relationship("Dataset", back_populates="records")
    language = relationship("Language", back_populates="records")
