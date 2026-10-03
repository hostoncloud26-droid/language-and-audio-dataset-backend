# 🚀 Language & Audio Dataset Platform - Backend API

High-performance asynchronous backend service built with [FastAPI](https://fastapi.tiangolo.com/), [PostgreSQL](https://www.postgresql.org/) (via SQLAlchemy ORM), [Chibisafe](https://chibisafe.app/) remote file storage integration, and OmniVoice speech synthesis engine.

---

## 🌟 Key Highlights

- **⚡ Fast & Modern**: Built with FastAPI and Uvicorn for asynchronous I/O and low latency.
- **🗄️ PostgreSQL Database**: Automatic schema creation and connection health status via SQLAlchemy ORM.
- **☁️ Remote Chibisafe File Server**: Direct multipart audio upload (`POST /api/upload`), album categorization (`POST /api/files/album/add`), and remote audio deletion (`DELETE /api/audio/{id}`).
- **🎙️ OmniVoice & Neural Speech Synthesis**: Endpoint ready for TTS text-to-speech generation with high-fidelity multi-lingual audio synthesis.
- **🔐 JWT Authentication**: Token-based security, bcrypt password hashing, and user profile management.
- **📖 Auto-Generated Documentation**: Interactive Swagger UI (`/docs`) and ReDoc (`/redoc`).

---

## 📁 Repository Structure

```
backend/
├── media/
│   ├── uploads/            # Temporary local storage for recordings/uploads
│   └── generated/          # Storage for synthesized audio files
├── audio_generator.py      # Neural TTS and audio waveform generation
├── chibisafe_service.py    # Remote Chibisafe file server upload & delete integration
├── config.py               # Environment configuration and paths
├── database.py             # SQLAlchemy engine, session maker, and DB health check
├── main.py                 # FastAPI application routes and middleware
├── models.py               # SQLAlchemy database models
├── omnivoice_service.py    # OmniVoice remote streaming API integration
├── requirements.txt        # Python dependency manifest
├── run_server.py           # Standalone launcher script with connection diagnostics
├── schemas.py              # Pydantic request and response schemas
├── security.py             # JWT token handling and bcrypt password hashing
├── seed.py                 # Initial data seeding for languages and datasets
├── .env.example            # Environment variables template
└── .gitignore              # Git ignore rules for Python, venv, and media
```

---

## ⚙️ Installation & Setup

### 1. Prerequisites
- Python 3.10 or higher
- `pip` package manager
- (Optional) `virtualenv`

### 2. Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configure your credentials inside `.env`:
```env
# Server Network Configuration
HOST=0.0.0.0
FASTAPI_PORT=8000
DEBUG=True

# PostgreSQL Database Connection
DATABASE_URL=postgresql://postgres:<YOUR_PASSWORD>@72.61.239.30:8909/postgres

# Remote Storage Server (Chibisafe) Configuration
CHIBISAFE_URL=http://chibisafe-js70kfifmck6m9b4lzbe5hko.72.61.239.30.sslip.io
CHIBISAFE_API_KEY=<YOUR_CHIBISAFE_API_KEY>
CHIBISAFE_ALBUM_UUID=63219c42-774f-4eae-8448-7e75d446a63a

# Remote Voice Generation Server (OmniVoice) Configuration
OMNIVOICE_URL=http://47.29.133.221:32149

# JWT Security
JWT_SECRET_KEY=vdf-dataset-platform-super-secure-jwt-key-2026-xyz-32bytes!
JWT_EXPIRE_MINUTES=1440
```

---

## 🏃 Running the Backend

### Option A: Using the Launcher Script (Recommended)
This script performs a pre-flight database connection test and outputs interactive URLs:
```bash
python run_server.py
```

### Option B: Using Uvicorn Directly
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📡 API Endpoints & Documentation

Once the server is running:
- **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Database Status**: [http://localhost:8000/api/db/status](http://localhost:8000/api/db/status)
- **Health Check**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### Primary API Routes:
| Route | Method | Description |
|---|---|---|
| `/api/auth/login` | POST | User login, returns JWT token |
| `/api/auth/register` | POST | Register a new user |
| `/api/languages` | GET, POST | List and create dataset languages |
| `/api/datasets` | GET, POST | List and create datasets |
| `/api/datasets/{id}/records` | GET, POST | Get and add audio records to a dataset |
| `/api/records/{id}` | PUT, DELETE | Update or delete a dataset record |
| `/api/upload` | POST | Upload audio file directly to remote Chibisafe server |
| `/api/audio/{record_id}` | DELETE | Delete audio record from both database and remote Chibisafe server |
| `/api/generate` | POST | Generate audio via OmniVoice / Neural TTS engine |
| `/api/db/status` | GET | Check PostgreSQL connection health |

---

## 🐙 Push to GitHub as a Separate Repository

To publish this backend as its own independent GitHub repository:

```bash
# 1. Navigate to the backend directory
cd backend

# 2. Initialize a new Git repository
git init

# 3. Stage all files (respects .gitignore)
git add .
git commit -m "feat: initial backend commit for Language & Audio Dataset Platform"

# 4. Set default branch to main
git branch -M main

# 5. Connect to your GitHub repository (replace with your repo URL)
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_BACKEND_REPO_NAME>.git

# 6. Push to GitHub
git push -u origin main
```
