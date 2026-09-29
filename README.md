# PhysioFlex

**AI- & IoT-assisted Digital Physiotherapy and Rehabilitation Platform**

PhysioFlex provides three independent role-specific portals (Doctor, Physiotherapist, Patient) connected through a shared backend. It supports:

- Camera-based pose estimation (MediaPipe) for joint angles, repetition counting and movement quality
- IoT-ready architecture (ESP32 + MPU6050 data can be posted to `/api/sessions`)
- Longitudinal progress tracking (ROM, pain, adherence)
- Clinical notes, assessments and alerts
- Decision-support information only (no autonomous diagnosis)

## Quick Start (Local)

```bash
cd physioflex_app
pip install -r requirements.txt
# or: pip install fastapi uvicorn python-multipart python-jose passlib bcrypt pydantic python-dotenv websockets aiofiles jinja2
export PATH=$PATH:/root/.local/bin   # if needed
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**

### Demo Accounts (password for all: `password123`)

| Role              | Email                     |
|-------------------|---------------------------|
| Doctor            | doctor@physioflex.com     |
| Physiotherapist   | physio@physioflex.com     |
| Patient           | patient@physioflex.com    |

## Features Implemented

### Doctor Portal (`/doctor`)
- Assigned patients overview
- Clinical metrics (pain, ROM, adherence)
- Abnormal movement alerts
- Exercise session history
- Clinical notes

### Physiotherapist Portal (`/physio`)
- Patient assessment entry
- View / create rehabilitation plans
- Monitor exercise sessions (camera + IoT source)
- Progress and notes

### Patient Portal (`/patient`)
- Today's plan with one-click start
- Personal progress charts
- Session history

### Live Exercise (`/patient/exercise`)
- Real-time webcam + MediaPipe Pose
- Live knee angle, repetition counter, quality feedback
- Pain slider + complete session → saved to backend

## Architecture

```
Patient (Camera / IoT)
        ↓
   PhysioFlex API (FastAPI)
        ↓
   JSON Database (data/db.json)
        ↓
  Doctor  ·  Physiotherapist
```

- Auth: JWT (Bearer token)
- Storage: file-based JSON (easy to replace with MongoDB Atlas)
- Real-time: WebSocket endpoint `/ws/session/{patient_id}` ready for live dashboards
- Frontend: server-rendered Jinja2 + Tailwind CDN + vanilla JS

## Deploy (Free Options)

### Render / Railway / Fly.io

1. Push this folder to a GitHub repo
2. Create a new Web Service
3. Build: `pip install -r requirements.txt`
4. Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variable if desired: `SECRET_KEY=your-long-random-string`

### Docker (optional)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## IoT Integration (ESP32 + MPU6050)

Post sensor-derived sessions to the same endpoint:

```http
POST /api/sessions
Authorization: Bearer <patient-or-physio-token>
Content-Type: application/json

{
  "plan_id": "plan001",
  "exercise_id": "ex001",
  "exercise_name": "Seated Knee Extension",
  "reps_completed": 10,
  "target_reps": 12,
  "sets_completed": 3,
  "max_rom": 118,
  "avg_rom": 112,
  "quality": "Good",
  "pain_score": 3,
  "duration_seconds": 240,
  "source": "iot"
}
```

## Accuracy Notes

This demo uses MediaPipe Pose for joint-angle estimation. Report accuracy carefully:

- Measure ROM error against a goniometer on a test set
- Measure repetition counting error (e.g. ground-truth 20 → system 19)
- Do **not** claim overall “98% accuracy” without a proper evaluation dataset

## Project Structure

```
physioflex_app/
├── main.py              # FastAPI app + all routes
├── auth.py              # JWT helpers
├── database.py          # JSON DB + seed data
├── requirements.txt
├── data/db.json         # Auto-created on first run
├── static/js/api.js     # Frontend API client
└── templates/           # HTML portals
    ├── index.html
    ├── login.html
    ├── doctor.html
    ├── physio.html
    ├── patient.html
    └── exercise.html
```

## License

Educational / demonstration project. Clinical decisions remain the responsibility of qualified healthcare professionals.
