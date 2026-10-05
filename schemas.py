from typing import Optional, List, Union
from pydantic import BaseModel, Field

# Auth schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class SendOtpRequest(BaseModel):
    email: str

class SendOtpResponse(BaseModel):
    success: bool
    message: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    role: Optional[str] = "Dataset Specialist"
    otp: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    name: str
    role: str
    avatar: Optional[str] = None

class LoginResponse(BaseModel):
    token: str
    user: UserResponse

# Language schemas
class LanguageCreate(BaseModel):
    name: str
    code: Optional[str] = None
    status: Optional[str] = "Active"

class LanguageUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    status: Optional[str] = None

class LanguageResponse(BaseModel):
    id: int
    name: str
    status: str
    code: Optional[str] = None

    class Config:
        from_attributes = True

# Dataset Record schemas
class DatasetRecordCreate(BaseModel):
    text: str
    audio_url: str
    language_id: Union[int, str]
    language_name: Optional[str] = None
    duration: Optional[float] = 0.0

class DatasetRecordUpdate(BaseModel):
    text: Optional[str] = None
    audio_url: Optional[str] = None
    language_id: Optional[Union[int, str]] = None
    language_name: Optional[str] = None

class DatasetRecordResponse(BaseModel):
    id: str
    dataset_id: str
    text: str
    audio_url: str
    language_id: int
    language_name: Optional[str] = None
    duration: Optional[float] = 0.0
    created_at: str

    class Config:
        from_attributes = True

# Dataset schemas
class DatasetCreate(BaseModel):
    name: str
    language_id: int
    description: Optional[str] = None

class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class DatasetResponse(BaseModel):
    id: str
    name: str
    language_id: int
    language_name: Optional[str] = None
    record_count: int = 0
    created_at: str

    class Config:
        from_attributes = True

class DatasetDetailResponse(BaseModel):
    dataset: DatasetResponse
    records: List[DatasetRecordResponse] = []

# Audio Upload & Generate Schemas
class AudioUploadResponse(BaseModel):
    audio_url: str
    filename: str
    duration: float
    uuid: Optional[str] = None

class AudioGenerateRequest(BaseModel):
    text: str
    language_id: Union[int, str] = 1
    language_name: Optional[str] = None
    lang_code: Optional[str] = None
    ref_audio: Optional[str] = "reference.mp3"

class AudioGenerateResponse(BaseModel):
    audio_url: str
    filename: str
    duration: float
    engine: Optional[str] = None
    lang_code: Optional[str] = None


# Database Status Schema
class DbStatusResponse(BaseModel):
    connected: bool
    database: Optional[str] = None
    user: Optional[str] = None
    version: Optional[str] = None
    url_masked: Optional[str] = None
    error: Optional[str] = None
    counts: Optional[dict] = None

class SuccessResponse(BaseModel):
    success: bool
    message: str
