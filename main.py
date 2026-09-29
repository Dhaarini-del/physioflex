"""
PhysioFlex – AI & IoT Assisted Digital Physiotherapy Platform
Full CRUD + real-time portal updates + dataset exercises
"""
from fastapi import FastAPI, Request, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import asyncio
import os
from pathlib import Path

from database import get_db, save_db, generate_id, seed_if_empty, _now, append_event
from auth import (
    verify_password, create_access_token, get_current_user,
    require_role, TokenData, UserOut,
)

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="PhysioFlex API", version="1.1.0")

_default_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()] or _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------- Real-time connection manager ----------
class ConnectionManager:
    def __init__(self):
        self.by_role: Dict[str, list] = {"doctor": [], "physiotherapist": [], "patient": []}
        self.by_patient: Dict[str, list] = {}

    async def connect(self, websocket: WebSocket, role: str, patient_id: str = None):
        await websocket.accept()
        self.by_role.setdefault(role, []).append(websocket)
        if patient_id:
            self.by_patient.setdefault(patient_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, role: str, patient_id: str = None):
        if role in self.by_role and websocket in self.by_role[role]:
            self.by_role[role].remove(websocket)
        if patient_id and patient_id in self.by_patient and websocket in self.by_patient[patient_id]:
            self.by_patient[patient_id].remove(websocket)

    async def broadcast_roles(self, roles: list, message: dict):
        dead = []
        for role in roles:
            for ws in list(self.by_role.get(role, [])):
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append((role, ws))
        for role, ws in dead:
            if ws in self.by_role.get(role, []):
                self.by_role[role].remove(ws)

    async def broadcast_patient(self, patient_id: str, message: dict):
        for ws in list(self.by_patient.get(patient_id, [])):
            try:
                await ws.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.on_event("startup")
async def startup():
    seed_if_empty()
    print("PhysioFlex 1.1 started")
    print("  admin@physioflex.com  / password123")
    print("  doctor@physioflex.com / password123")
    print("  physio@physioflex.com / password123")
    print("  patient@physioflex.com / password123")


# ---------- Auth ----------
class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    db = get_db()
    user = next((u for u in db["users"] if u["email"] == body.email), None)
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(
        {"sub": user["id"], "role": user["role"], "email": user["email"]}
    )
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user["id"], email=user["email"], name=user["name"], role=user["role"]),
    )


@app.get("/api/auth/me", response_model=UserOut)
async def me(user: TokenData = Depends(get_current_user)):
    db = get_db()
    u = next((x for x in db["users"] if x["id"] == user.user_id), None)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=u["id"], email=u["email"], name=u["name"], role=u["role"])


# ---------- Exercise catalog (dataset) ----------
@app.get("/api/exercises")
async def list_exercises(user: TokenData = Depends(get_current_user)):
    db = get_db()
    return db.get("exercises", [])


# ---------- Patients CRUD ----------
def _can_access_patient(user: TokenData, patient: dict) -> bool:
    if user.role == "patient":
        return patient.get("user_id") == user.user_id or patient.get("id") == user.user_id
    if user.role == "doctor":
        return patient.get("doctor_id") == user.user_id
    if user.role == "physiotherapist":
        return patient.get("physio_id") == user.user_id
    return False


@app.get("/api/patients")
async def list_patients(user: TokenData = Depends(get_current_user)):
    db = get_db()
    if user.role == "doctor":
        return [p for p in db["patients"] if p.get("doctor_id") == user.user_id]
    if user.role == "physiotherapist":
        return [p for p in db["patients"] if p.get("physio_id") == user.user_id]
    if user.role == "patient":
        return [p for p in db["patients"] if p.get("user_id") == user.user_id or p.get("id") == user.user_id]
    return []


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    patient = next((p for p in db["patients"] if p["id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_access_patient(user, patient):
        raise HTTPException(status_code=403, detail="Access denied")
    return patient


class PatientCreate(BaseModel):
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    condition: Optional[str] = ""
    summary: Optional[str] = ""
    operation: Optional[str] = ""
    reason_of_operation: Optional[str] = ""
    surgery_date: Optional[str] = None
    target_rom: Optional[float] = 120
    status: Optional[str] = "active"
    # assign to current doctor/physio automatically when they create


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    condition: Optional[str] = None
    summary: Optional[str] = None
    operation: Optional[str] = None
    reason_of_operation: Optional[str] = None
    surgery_date: Optional[str] = None
    current_pain: Optional[int] = None
    current_rom: Optional[float] = None
    target_rom: Optional[float] = None
    adherence_percent: Optional[int] = None
    status: Optional[str] = None
    doctor_id: Optional[str] = None
    physio_id: Optional[str] = None


@app.post("/api/patients")
async def create_patient(
    body: PatientCreate,
    user: TokenData = Depends(require_role("doctor", "physiotherapist", "admin")),
):
    """Doctor/Physio register a clinical patient record.
    Login credentials are issued only by Admin (see /api/admin/users).
    A credential request is sent to admin automatically.
    """
    db = get_db()
    db.setdefault("credential_requests", [])
    pid = generate_id("pat")
    patient = {
        "id": pid,
        "user_id": None,  # no login until admin provisions
        "name": body.name,
        "age": body.age,
        "gender": body.gender,
        "email": body.email or "",
        "condition": body.condition or "",
        "summary": body.summary or "",
        "operation": body.operation or "",
        "reason_of_operation": body.reason_of_operation or "",
        "surgery_date": body.surgery_date,
        "doctor_id": user.user_id if user.role == "doctor" else (body.dict().get("doctor_id") or "doc001"),
        "physio_id": user.user_id if user.role == "physiotherapist" else "phy001",
        "current_pain": 0,
        "current_rom": 0,
        "target_rom": body.target_rom or 120,
        "adherence_percent": 0,
        "status": "pending_credentials" if user.role != "admin" else (body.status or "active"),
        "created_at": _now(),
        "updated_at": _now(),
        "requested_by": user.user_id,
        "requested_by_role": user.role,
    }
    if user.role == "doctor":
        patient["doctor_id"] = user.user_id
    db["patients"].append(patient)

    # Notify admin to issue login credentials
    req = {
        "id": generate_id("cr"),
        "type": "patient_credentials",
        "patient_id": pid,
        "patient_name": body.name,
        "email": body.email or "",
        "requested_by": user.user_id,
        "requested_by_role": user.role,
        "status": "pending",
        "created_at": _now(),
    }
    db["credential_requests"].append(req)
    save_db(db)
    await manager.broadcast_roles(["admin", "doctor", "physiotherapist"], {
        "event": "patient_created", "patient_id": pid, "data": patient,
        "message": f"New patient {body.name} – admin must issue login credentials",
    })
    await manager.broadcast_roles(["admin"], {
        "event": "credential_request", "data": req,
        "message": f"Credential request for patient {body.name}",
    })
    return patient


@app.put("/api/patients/{patient_id}")
async def update_patient(
    patient_id: str,
    body: PatientUpdate,
    user: TokenData = Depends(require_role("doctor", "physiotherapist")),
):
    db = get_db()
    patient = next((p for p in db["patients"] if p["id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_access_patient(user, patient):
        raise HTTPException(status_code=403, detail="Access denied")
    data = body.dict(exclude_unset=True)
    for k, v in data.items():
        if v is not None:
            patient[k] = v
    patient["updated_at"] = _now()
    save_db(db)
    append_event("patient_updated", {"patient": patient}, patient_id=patient_id)
    await manager.broadcast_roles(["doctor", "physiotherapist", "patient"], {
        "event": "patient_updated", "patient_id": patient_id, "data": patient,
    })
    return patient


@app.delete("/api/patients/{patient_id}")
async def delete_patient(
    patient_id: str,
    user: TokenData = Depends(require_role("doctor", "physiotherapist")),
):
    db = get_db()
    patient = next((p for p in db["patients"] if p["id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if not _can_access_patient(user, patient):
        raise HTTPException(status_code=403, detail="Access denied")
    db["patients"] = [p for p in db["patients"] if p["id"] != patient_id]
    # cascade soft: remove plans/sessions/notes for this patient optional – keep history
    save_db(db)
    append_event("patient_deleted", {"patient_id": patient_id}, patient_id=patient_id)
    await manager.broadcast_roles(["doctor", "physiotherapist"], {
        "event": "patient_deleted", "patient_id": patient_id,
    })
    return {"ok": True, "deleted": patient_id}


# ---------- Assessments ----------
@app.get("/api/patients/{patient_id}/assessments")
async def get_assessments(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    return [a for a in db["assessments"] if a["patient_id"] == patient_id]


class AssessmentCreate(BaseModel):
    pain_score: int
    rom_knee_flexion: float
    rom_knee_extension: float
    notes: str = ""


@app.post("/api/patients/{patient_id}/assessments")
async def create_assessment(
    patient_id: str,
    body: AssessmentCreate,
    user: TokenData = Depends(require_role("physiotherapist")),
):
    db = get_db()
    assessment = {
        "id": generate_id("asm"),
        "patient_id": patient_id,
        "physio_id": user.user_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pain_score": body.pain_score,
        "rom_knee_flexion": body.rom_knee_flexion,
        "rom_knee_extension": body.rom_knee_extension,
        "notes": body.notes,
        "created_at": _now(),
    }
    db["assessments"].append(assessment)
    for p in db["patients"]:
        if p["id"] == patient_id:
            p["current_pain"] = body.pain_score
            p["current_rom"] = body.rom_knee_flexion
            p["updated_at"] = _now()
            break
    save_db(db)
    await manager.broadcast_roles(["doctor", "physiotherapist"], {
        "event": "assessment_created", "patient_id": patient_id, "data": assessment,
    })
    return assessment


# ---------- Rehab Plans + assign exercises ----------
@app.get("/api/patients/{patient_id}/plans")
async def get_plans(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    return [p for p in db["rehab_plans"] if p["patient_id"] == patient_id]


class ExerciseInPlan(BaseModel):
    exercise_id: str
    name: str
    sets: int = 3
    reps: int = 10
    target_rom: float = 90
    frequency: str = "Daily"
    instructions: str = ""


class PlanCreate(BaseModel):
    title: str
    start_date: str
    end_date: str
    exercises: List[ExerciseInPlan] = []


class PlanUpdate(BaseModel):
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: Optional[str] = None
    exercises: Optional[List[ExerciseInPlan]] = None


@app.post("/api/patients/{patient_id}/plans")
async def create_plan(
    patient_id: str,
    body: PlanCreate,
    user: TokenData = Depends(require_role("physiotherapist")),
):
    db = get_db()
    plan = {
        "id": generate_id("plan"),
        "patient_id": patient_id,
        "physio_id": user.user_id,
        "title": body.title,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "status": "active",
        "exercises": [e.dict() for e in body.exercises],
        "created_at": _now(),
        "updated_at": _now(),
    }
    db["rehab_plans"].append(plan)
    save_db(db)
    append_event("plan_created", {"plan": plan}, patient_id=patient_id)
    await manager.broadcast_roles(["doctor", "physiotherapist", "patient"], {
        "event": "plan_created", "patient_id": patient_id, "data": plan,
    })
    return plan


@app.put("/api/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    body: PlanUpdate,
    user: TokenData = Depends(require_role("physiotherapist")),
):
    db = get_db()
    plan = next((p for p in db["rehab_plans"] if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    data = body.dict(exclude_unset=True)
    if "exercises" in data and data["exercises"] is not None:
        plan["exercises"] = [e if isinstance(e, dict) else e.dict() for e in data["exercises"]]
        del data["exercises"]
    for k, v in data.items():
        if v is not None:
            plan[k] = v
    plan["updated_at"] = _now()
    save_db(db)
    await manager.broadcast_roles(["doctor", "physiotherapist", "patient"], {
        "event": "plan_updated", "patient_id": plan["patient_id"], "data": plan,
    })
    return plan


@app.delete("/api/plans/{plan_id}")
async def delete_plan(
    plan_id: str,
    user: TokenData = Depends(require_role("physiotherapist")),
):
    db = get_db()
    plan = next((p for p in db["rehab_plans"] if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    pid = plan["patient_id"]
    db["rehab_plans"] = [p for p in db["rehab_plans"] if p["id"] != plan_id]
    save_db(db)
    await manager.broadcast_roles(["doctor", "physiotherapist", "patient"], {
        "event": "plan_deleted", "patient_id": pid, "plan_id": plan_id,
    })
    return {"ok": True}


# ---------- Sessions ----------
@app.get("/api/patients/{patient_id}/sessions")
async def get_sessions(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    sessions = [s for s in db["sessions"] if s["patient_id"] == patient_id]
    sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return sessions


class SessionCreate(BaseModel):
    plan_id: str
    exercise_id: str
    exercise_name: str
    reps_completed: int
    target_reps: int
    sets_completed: int = 1
    max_rom: float
    avg_rom: float
    quality: str = "Fair"
    pain_score: int = 0
    duration_seconds: int = 0
    source: str = "camera"


@app.post("/api/sessions")
async def create_session(
    body: SessionCreate,
    user: TokenData = Depends(require_role("patient", "physiotherapist")),
):
    db = get_db()
    if user.role == "patient":
        patient_id = user.user_id
        # map user_id to patient id
        pmatch = next((p for p in db["patients"] if p.get("user_id") == user.user_id or p["id"] == user.user_id), None)
        if pmatch:
            patient_id = pmatch["id"]
    else:
        patient_id = "pat001"

    session = {
        "id": generate_id("ses"),
        "patient_id": patient_id,
        "plan_id": body.plan_id,
        "exercise_id": body.exercise_id,
        "exercise_name": body.exercise_name,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reps_completed": body.reps_completed,
        "target_reps": body.target_reps,
        "sets_completed": body.sets_completed,
        "max_rom": body.max_rom,
        "avg_rom": body.avg_rom,
        "quality": body.quality,
        "pain_score": body.pain_score,
        "duration_seconds": body.duration_seconds,
        "source": body.source,
        "created_at": _now(),
    }
    db["sessions"].append(session)

    for p in db["patients"]:
        if p["id"] == patient_id:
            p["current_pain"] = body.pain_score
            p["current_rom"] = max(p.get("current_rom") or 0, body.max_rom)
            p["updated_at"] = _now()
            break

    total_target = total_done = 0
    for s in db["sessions"]:
        if s["patient_id"] == patient_id:
            total_target += s.get("target_reps", 0) * max(s.get("sets_completed", 1), 1)
            total_done += s.get("reps_completed", 0)
    if total_target > 0:
        for p in db["patients"]:
            if p["id"] == patient_id:
                p["adherence_percent"] = min(100, int((total_done / total_target) * 100))
                break

    save_db(db)
    append_event("session_completed", {"session": session}, patient_id=patient_id)
    # REAL-TIME: notify doctor + physio immediately
    await manager.broadcast_roles(["doctor", "physiotherapist"], {
        "event": "session_completed",
        "patient_id": patient_id,
        "data": session,
        "message": f"Patient completed {body.exercise_name}: {body.reps_completed}/{body.target_reps} reps, ROM {body.max_rom}°, quality {body.quality}",
    })
    return session


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: TokenData = Depends(require_role("doctor", "physiotherapist")),
):
    db = get_db()
    ses = next((s for s in db["sessions"] if s["id"] == session_id), None)
    if not ses:
        raise HTTPException(status_code=404, detail="Session not found")
    pid = ses["patient_id"]
    db["sessions"] = [s for s in db["sessions"] if s["id"] != session_id]
    save_db(db)
    await manager.broadcast_roles(["doctor", "physiotherapist"], {
        "event": "session_deleted", "patient_id": pid, "session_id": session_id,
    })
    return {"ok": True}


# ---------- Notes ----------
@app.get("/api/patients/{patient_id}/notes")
async def get_notes(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    return [n for n in db["notes"] if n["patient_id"] == patient_id]


class NoteCreate(BaseModel):
    content: str


@app.post("/api/patients/{patient_id}/notes")
async def create_note(
    patient_id: str,
    body: NoteCreate,
    user: TokenData = Depends(require_role("doctor", "physiotherapist")),
):
    db = get_db()
    note = {
        "id": generate_id("note"),
        "patient_id": patient_id,
        "author_id": user.user_id,
        "author_role": user.role,
        "content": body.content,
        "created_at": _now(),
    }
    db["notes"].append(note)
    save_db(db)
    await manager.broadcast_roles(["doctor", "physiotherapist", "patient"], {
        "event": "note_added", "patient_id": patient_id, "data": note,
        "message": f"New note on patient record",
    })
    return note


# ---------- Alerts ----------
@app.get("/api/patients/{patient_id}/alerts")
async def get_alerts(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    return [a for a in db["alerts"] if a["patient_id"] == patient_id]


# ---------- Dashboards ----------
@app.get("/api/dashboard/doctor")
async def doctor_dashboard(user: TokenData = Depends(require_role("doctor"))):
    db = get_db()
    patients = [p for p in db["patients"] if p.get("doctor_id") == user.user_id]
    alerts = [a for a in db["alerts"] if not a.get("resolved") and any(p["id"] == a["patient_id"] for p in patients)]
    return {
        "patient_count": len(patients),
        "patients": patients,
        "active_alerts": alerts,
        "recent_sessions": sorted(
            [s for s in db["sessions"] if any(p["id"] == s["patient_id"] for p in patients)],
            key=lambda x: x.get("created_at", ""), reverse=True,
        )[:15],
        "recent_events": sorted(db.get("events", []), key=lambda x: x.get("created_at", ""), reverse=True)[:20],
    }


@app.get("/api/dashboard/physio")
async def physio_dashboard(user: TokenData = Depends(require_role("physiotherapist"))):
    db = get_db()
    patients = [p for p in db["patients"] if p.get("physio_id") == user.user_id]
    return {
        "patient_count": len(patients),
        "patients": patients,
        "plans": [p for p in db["rehab_plans"] if p.get("physio_id") == user.user_id],
        "exercises": db.get("exercises", []),
        "recent_sessions": sorted(
            [s for s in db["sessions"] if any(p["id"] == s["patient_id"] for p in patients)],
            key=lambda x: x.get("created_at", ""), reverse=True,
        )[:15],
    }


@app.get("/api/dashboard/patient")
async def patient_dashboard(user: TokenData = Depends(require_role("patient"))):
    db = get_db()
    patient = next((p for p in db["patients"] if p.get("user_id") == user.user_id or p["id"] == user.user_id), None)
    if not patient:
        return {"patient": None, "active_plans": [], "recent_sessions": []}
    plans = [p for p in db["rehab_plans"] if p["patient_id"] == patient["id"] and p["status"] == "active"]
    sessions = sorted(
        [s for s in db["sessions"] if s["patient_id"] == patient["id"]],
        key=lambda x: x.get("created_at", ""), reverse=True,
    )[:15]
    return {"patient": patient, "active_plans": plans, "recent_sessions": sessions}


@app.get("/api/patients/{patient_id}/progress")
async def get_progress(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    sessions = [s for s in db["sessions"] if s["patient_id"] == patient_id]
    sessions.sort(key=lambda x: x.get("date", ""))
    rom_trend = [{"date": s["date"], "rom": s["max_rom"]} for s in sessions]
    pain_trend = [{"date": s["date"], "pain": s["pain_score"]} for s in sessions]
    return {
        "rom_trend": rom_trend,
        "pain_trend": pain_trend,
        "total_sessions": len(sessions),
    }


# ---------- WebSocket real-time ----------
@app.websocket("/ws/{role}")
async def websocket_role(websocket: WebSocket, role: str):
    """Connect as doctor | physiotherapist | patient for live updates."""
    await manager.connect(websocket, role)
    try:
        while True:
            data = await websocket.receive_json()
            # allow clients to ping / subscribe to patient
            if data.get("type") == "subscribe_patient":
                pid = data.get("patient_id")
                if pid:
                    manager.by_patient.setdefault(pid, []).append(websocket)
            elif data.get("type") == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, role)


@app.websocket("/ws/session/{patient_id}")
async def websocket_session(websocket: WebSocket, patient_id: str):
    await manager.connect(websocket, "patient", patient_id)
    try:
        while True:
            data = await websocket.receive_json()
            # live metrics during exercise → broadcast to clinicians
            await manager.broadcast_roles(["doctor", "physiotherapist"], {
                "event": "live_metrics",
                "patient_id": patient_id,
                "data": data,
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, "patient", patient_id)




@app.get("/api/admin/credential-requests")
async def list_credential_requests(user: TokenData = Depends(require_role("admin"))):
    db = get_db()
    return sorted(db.get("credential_requests", []), key=lambda x: x.get("created_at", ""), reverse=True)


class ProvisionCredentials(BaseModel):
    email: str
    password: str = "password123"
    name: Optional[str] = None


@app.post("/api/admin/credential-requests/{req_id}/provision")
async def provision_credentials(req_id: str, body: ProvisionCredentials, user: TokenData = Depends(require_role("admin"))):
    """Admin issues login credentials for a pending patient request."""
    from auth import get_password_hash
    db = get_db()
    req = next((r for r in db.get("credential_requests", []) if r["id"] == req_id), None)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if any(u["email"] == body.email for u in db["users"]):
        raise HTTPException(status_code=400, detail="Email already in use")
    uid = req.get("patient_id") or generate_id("pat")
    new_user = {
        "id": uid,
        "email": body.email,
        "password": get_password_hash(body.password or "password123"),
        "name": body.name or req.get("patient_name") or "Patient",
        "role": "patient",
        "created_at": _now(),
        "active": True,
    }
    db["users"].append(new_user)
    for p in db["patients"]:
        if p["id"] == req.get("patient_id"):
            p["user_id"] = uid
            p["email"] = body.email
            p["status"] = "active"
            p["updated_at"] = _now()
            break
    req["status"] = "provisioned"
    req["provisioned_email"] = body.email
    req["updated_at"] = _now()
    save_db(db)
    await manager.broadcast_roles(["admin", "doctor", "physiotherapist"], {
        "event": "credentials_provisioned", "patient_id": req.get("patient_id"),
        "message": f"Login created for {new_user['name']}",
    })
    return {"ok": True, "user": {k: v for k, v in new_user.items() if k != "password"}, "temp_password": body.password}


# ---------- Admin: user CRUD ----------
class AdminUserCreate(BaseModel):
    email: str
    password: str = "password123"
    name: str
    role: str  # admin | doctor | physiotherapist | patient
    specialty: Optional[str] = None
    license: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None


class AdminUserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    specialty: Optional[str] = None
    license: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    active: Optional[bool] = None


@app.get("/api/admin/users")
async def admin_list_users(user: TokenData = Depends(require_role("admin"))):
    db = get_db()
    out = []
    for u in db["users"]:
        item = {k: v for k, v in u.items() if k != "password"}
        out.append(item)
    return out


@app.post("/api/admin/users")
async def admin_create_user(body: AdminUserCreate, user: TokenData = Depends(require_role("admin"))):
    from auth import get_password_hash
    db = get_db()
    if any(u["email"] == body.email for u in db["users"]):
        raise HTTPException(status_code=400, detail="Email already registered")
    if body.role not in ("admin", "doctor", "physiotherapist", "patient"):
        raise HTTPException(status_code=400, detail="Invalid role")
    uid = generate_id(body.role[:3])
    new_user = {
        "id": uid,
        "email": body.email,
        "password": get_password_hash(body.password or "password123"),
        "name": body.name,
        "role": body.role,
        "created_at": _now(),
        "active": True,
    }
    if body.specialty:
        new_user["specialty"] = body.specialty
    if body.license:
        new_user["license"] = body.license
    if body.age is not None:
        new_user["age"] = body.age
    if body.gender:
        new_user["gender"] = body.gender
    db["users"].append(new_user)

    # Auto-create patient record for patient role
    if body.role == "patient":
        db["patients"].append({
            "id": uid, "user_id": uid, "name": body.name, "age": body.age,
            "gender": body.gender, "email": body.email,
            "condition": "", "summary": "", "operation": "", "reason_of_operation": "",
            "surgery_date": None, "doctor_id": "doc001", "physio_id": "phy001",
            "current_pain": 0, "current_rom": 0, "target_rom": 120, "adherence_percent": 0,
            "status": "active", "created_at": _now(), "updated_at": _now(),
        })
    save_db(db)
    await manager.broadcast_roles(["admin", "doctor", "physiotherapist"], {
        "event": "user_created", "data": {k: v for k, v in new_user.items() if k != "password"},
    })
    return {k: v for k, v in new_user.items() if k != "password"}


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: str, body: AdminUserUpdate, user: TokenData = Depends(require_role("admin"))):
    from auth import get_password_hash
    db = get_db()
    u = next((x for x in db["users"] if x["id"] == user_id), None)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.dict(exclude_unset=True)
    if "password" in data and data["password"]:
        u["password"] = get_password_hash(data["password"])
        del data["password"]
    for k, v in data.items():
        if v is not None:
            u[k] = v
    # sync patient name/email if patient
    if u["role"] == "patient":
        for p in db["patients"]:
            if p.get("user_id") == user_id or p["id"] == user_id:
                if "name" in data and data["name"]:
                    p["name"] = data["name"]
                if "email" in data and data["email"]:
                    p["email"] = data["email"]
                if "age" in data and data["age"] is not None:
                    p["age"] = data["age"]
                if "gender" in data and data["gender"]:
                    p["gender"] = data["gender"]
                p["updated_at"] = _now()
    save_db(db)
    return {k: v for k, v in u.items() if k != "password"}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: str, user: TokenData = Depends(require_role("admin"))):
    db = get_db()
    if user_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    u = next((x for x in db["users"] if x["id"] == user_id), None)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    db["users"] = [x for x in db["users"] if x["id"] != user_id]
    if u["role"] == "patient":
        db["patients"] = [p for p in db["patients"] if p.get("user_id") != user_id and p["id"] != user_id]
    save_db(db)
    await manager.broadcast_roles(["admin"], {"event": "user_deleted", "user_id": user_id})
    return {"ok": True, "deleted": user_id}


@app.get("/api/admin/stats")
async def admin_stats(user: TokenData = Depends(require_role("admin"))):
    db = get_db()
    roles = {}
    for u in db["users"]:
        roles[u["role"]] = roles.get(u["role"], 0) + 1
    return {
        "users": len(db["users"]),
        "patients": len(db["patients"]),
        "sessions": len(db["sessions"]),
        "plans": len(db["rehab_plans"]),
        "complaints_open": len([c for c in db.get("complaints", []) if c.get("status") != "resolved"]),
        "by_role": roles,
    }


# ---------- Complaints / Reports (misconduct) ----------
class ComplaintCreate(BaseModel):
    against_role: str  # doctor | physiotherapist | patient | admin | other
    against_name: str = ""
    against_user_id: Optional[str] = None
    category: str = "misconduct"  # misconduct | negligence | harassment | privacy | other
    subject: str
    description: str
    severity: str = "medium"  # low | medium | high


@app.get("/api/complaints")
async def list_complaints(user: TokenData = Depends(get_current_user)):
    db = get_db()
    all_c = db.get("complaints", [])
    if user.role == "admin":
        return sorted(all_c, key=lambda x: x.get("created_at", ""), reverse=True)
    # users see their own filed complaints
    return sorted(
        [c for c in all_c if c.get("filed_by_id") == user.user_id],
        key=lambda x: x.get("created_at", ""), reverse=True,
    )


@app.post("/api/complaints")
async def create_complaint(body: ComplaintCreate, user: TokenData = Depends(get_current_user)):
    db = get_db()
    db.setdefault("complaints", [])
    complaint = {
        "id": generate_id("cmp"),
        "filed_by_id": user.user_id,
        "filed_by_name": next((u["name"] for u in db["users"] if u["id"] == user.user_id), user.email),
        "filed_by_role": user.role,
        "against_role": body.against_role,
        "against_name": body.against_name,
        "against_user_id": body.against_user_id,
        "category": body.category,
        "subject": body.subject,
        "description": body.description,
        "severity": body.severity,
        "status": "open",
        "admin_notes": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    db["complaints"].append(complaint)
    save_db(db)
    append_event("complaint_filed", {"complaint_id": complaint["id"], "subject": body.subject}, patient_id=None)
    await manager.broadcast_roles(["admin"], {
        "event": "complaint_filed",
        "data": complaint,
        "message": f"New complaint by {complaint['filed_by_name']} ({user.role}): {body.subject}",
    })
    return complaint


class ComplaintUpdate(BaseModel):
    status: Optional[str] = None  # open | under_review | resolved | dismissed
    admin_notes: Optional[str] = None


@app.put("/api/complaints/{complaint_id}")
async def update_complaint(
    complaint_id: str,
    body: ComplaintUpdate,
    user: TokenData = Depends(require_role("admin")),
):
    db = get_db()
    c = next((x for x in db.get("complaints", []) if x["id"] == complaint_id), None)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if body.status is not None:
        c["status"] = body.status
    if body.admin_notes is not None:
        c["admin_notes"] = body.admin_notes
    c["updated_at"] = _now()
    c["reviewed_by"] = user.user_id
    save_db(db)
    return c




# ---------- Schedules / visit alerts ----------
class ScheduleCreate(BaseModel):
    patient_id: str
    title: str
    schedule_type: str = "exercise"  # exercise | visit | checkup | custom
    datetime: str  # ISO
    notes: str = ""
    created_by_role: Optional[str] = None


@app.get("/api/schedules")
async def list_schedules(user: TokenData = Depends(get_current_user)):
    db = get_db()
    items = db.get("schedules", [])
    if user.role == "patient":
        pid = user.user_id
        return [s for s in items if s.get("patient_id") == pid]
    if user.role == "doctor":
        pids = {p["id"] for p in db["patients"] if p.get("doctor_id") == user.user_id}
        return [s for s in items if s.get("patient_id") in pids]
    if user.role == "physiotherapist":
        pids = {p["id"] for p in db["patients"] if p.get("physio_id") == user.user_id}
        return [s for s in items if s.get("patient_id") in pids]
    return items


@app.post("/api/schedules")
async def create_schedule(body: ScheduleCreate, user: TokenData = Depends(require_role("doctor", "physiotherapist", "admin"))):
    db = get_db()
    db.setdefault("schedules", [])
    item = {
        "id": generate_id("sch"),
        "patient_id": body.patient_id,
        "title": body.title,
        "schedule_type": body.schedule_type,
        "datetime": body.datetime,
        "notes": body.notes,
        "created_by": user.user_id,
        "created_by_role": user.role,
        "status": "scheduled",
        "created_at": _now(),
    }
    db["schedules"].append(item)
    save_db(db)
    await manager.broadcast_roles(["patient", "doctor", "physiotherapist"], {
        "event": "schedule_created", "patient_id": body.patient_id, "data": item,
        "message": f"New schedule: {body.title} ({body.schedule_type})",
    })
    return item


# ---------- Doctor suggestions to physio ----------
class SuggestionCreate(BaseModel):
    patient_id: str
    operation_type: str = ""
    suggested_exercises: List[str] = []  # names or ids
    recommended_sessions: int = 10
    pain_notes: str = ""
    abnormality_notes: str = ""
    general_notes: str = ""


@app.get("/api/suggestions")
async def list_suggestions(user: TokenData = Depends(get_current_user)):
    db = get_db()
    items = db.get("suggestions", [])
    if user.role == "doctor":
        return [s for s in items if s.get("doctor_id") == user.user_id]
    if user.role == "physiotherapist":
        pids = {p["id"] for p in db["patients"] if p.get("physio_id") == user.user_id}
        return [s for s in items if s.get("patient_id") in pids]
    if user.role == "patient":
        return [s for s in items if s.get("patient_id") == user.user_id]
    return items


@app.post("/api/suggestions")
async def create_suggestion(body: SuggestionCreate, user: TokenData = Depends(require_role("doctor"))):
    db = get_db()
    db.setdefault("suggestions", [])
    item = {
        "id": generate_id("sug"),
        "patient_id": body.patient_id,
        "doctor_id": user.user_id,
        "operation_type": body.operation_type,
        "suggested_exercises": body.suggested_exercises,
        "recommended_sessions": body.recommended_sessions,
        "pain_notes": body.pain_notes,
        "abnormality_notes": body.abnormality_notes,
        "general_notes": body.general_notes,
        "status": "sent",
        "created_at": _now(),
    }
    db["suggestions"].append(item)
    # also update patient operation fields if provided
    for p in db["patients"]:
        if p["id"] == body.patient_id:
            if body.operation_type:
                p["operation"] = body.operation_type
            if body.abnormality_notes:
                p["summary"] = (p.get("summary") or "") + " | " + body.abnormality_notes
            p["updated_at"] = _now()
            break
    save_db(db)
    await manager.broadcast_roles(["physiotherapist", "doctor"], {
        "event": "suggestion_created", "patient_id": body.patient_id, "data": item,
        "message": f"Doctor suggestion for patient: {body.operation_type or 'rehab plan'}",
    })
    return item


# ---------- Patient alerts to clinicians ----------
class PatientAlertCreate(BaseModel):
    alert_type: str = "pain"  # pain | abnormality | emergency | general
    message: str
    severity: str = "medium"


@app.get("/api/patient-alerts")
async def list_patient_alerts(user: TokenData = Depends(get_current_user)):
    db = get_db()
    items = db.get("patient_alerts", [])
    if user.role == "patient":
        return [a for a in items if a.get("patient_id") == user.user_id]
    if user.role == "doctor":
        pids = {p["id"] for p in db["patients"] if p.get("doctor_id") == user.user_id}
        return [a for a in items if a.get("patient_id") in pids]
    if user.role == "physiotherapist":
        pids = {p["id"] for p in db["patients"] if p.get("physio_id") == user.user_id}
        return [a for a in items if a.get("patient_id") in pids]
    return items


@app.post("/api/patient-alerts")
async def create_patient_alert(body: PatientAlertCreate, user: TokenData = Depends(require_role("patient"))):
    db = get_db()
    db.setdefault("patient_alerts", [])
    item = {
        "id": generate_id("pal"),
        "patient_id": user.user_id,
        "alert_type": body.alert_type,
        "message": body.message,
        "severity": body.severity,
        "status": "open",
        "created_at": _now(),
    }
    db["patient_alerts"].append(item)
    save_db(db)
    await manager.broadcast_roles(["doctor", "physiotherapist"], {
        "event": "patient_alert", "patient_id": user.user_id, "data": item,
        "message": f"Patient alert ({body.alert_type}): {body.message[:80]}",
    })
    return item


# ---------- Live session booking ----------
class BookingCreate(BaseModel):
    with_role: str  # doctor | physiotherapist
    preferred_datetime: str
    reason: str = ""
    notes: str = ""


@app.get("/api/bookings")
async def list_bookings(user: TokenData = Depends(get_current_user)):
    db = get_db()
    items = db.get("bookings", [])
    if user.role == "patient":
        return [b for b in items if b.get("patient_id") == user.user_id]
    if user.role in ("doctor", "physiotherapist"):
        return [b for b in items if b.get("with_role") == user.role or b.get("assigned_to") == user.user_id]
    return items


@app.post("/api/bookings")
async def create_booking(body: BookingCreate, user: TokenData = Depends(require_role("patient"))):
    db = get_db()
    db.setdefault("bookings", [])
    item = {
        "id": generate_id("bk"),
        "patient_id": user.user_id,
        "with_role": body.with_role,
        "preferred_datetime": body.preferred_datetime,
        "reason": body.reason,
        "notes": body.notes,
        "status": "requested",
        "created_at": _now(),
    }
    db["bookings"].append(item)
    save_db(db)
    roles = ["doctor"] if body.with_role == "doctor" else ["physiotherapist"]
    await manager.broadcast_roles(roles + ["patient"], {
        "event": "booking_requested", "patient_id": user.user_id, "data": item,
        "message": f"Live session requested with {body.with_role}",
    })
    return item


class BookingUpdate(BaseModel):
    status: str  # requested | confirmed | completed | cancelled
    assigned_to: Optional[str] = None
    meeting_link: Optional[str] = None


@app.put("/api/bookings/{booking_id}")
async def update_booking(booking_id: str, body: BookingUpdate, user: TokenData = Depends(require_role("doctor", "physiotherapist", "admin"))):
    db = get_db()
    b = next((x for x in db.get("bookings", []) if x["id"] == booking_id), None)
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    b["status"] = body.status
    if body.assigned_to:
        b["assigned_to"] = body.assigned_to
    if body.meeting_link:
        b["meeting_link"] = body.meeting_link
    b["updated_at"] = _now()
    save_db(db)
    await manager.broadcast_roles(["patient", "doctor", "physiotherapist"], {
        "event": "booking_updated", "patient_id": b["patient_id"], "data": b,
    })
    return b


# ---------- Voice messages (base64 audio or text transcript) ----------
class VoiceMessageCreate(BaseModel):
    to_role: str = "physiotherapist"  # doctor | physiotherapist | patient
    to_user_id: Optional[str] = None
    audio_base64: Optional[str] = None
    transcript: str = ""
    duration_seconds: int = 0


@app.get("/api/voice-messages")
async def list_voice_messages(user: TokenData = Depends(get_current_user)):
    db = get_db()
    items = db.get("voice_messages", [])
    # Everyone sees messages they sent or received
    out = []
    for m in items:
        if m.get("from_id") == user.user_id:
            out.append(m)
        elif m.get("to_user_id") == user.user_id:
            out.append(m)
        elif m.get("to_role") == user.role:
            out.append(m)
    # strip large audio from list
    clean = []
    for m in out:
        c = dict(m)
        if c.get("audio_base64") and len(c["audio_base64"]) > 200:
            c["has_audio"] = True
            c["audio_base64"] = None
        clean.append(c)
    return sorted(clean, key=lambda x: x.get("created_at", ""), reverse=True)


@app.post("/api/voice-messages")
async def create_voice_message(body: VoiceMessageCreate, user: TokenData = Depends(get_current_user)):
    db = get_db()
    db.setdefault("voice_messages", [])
    transcript = (body.transcript or "").strip()
    audio = body.audio_base64
    # Cap audio size (~300KB base64) to avoid payload failures
    if audio and len(audio) > 400000:
        audio = None
        if not transcript:
            transcript = "[Voice clip too large – please type a short message]"
    if not transcript and not audio:
        raise HTTPException(status_code=400, detail="Please record audio or type a message")
    item = {
        "id": generate_id("vm"),
        "from_id": user.user_id,
        "from_role": user.role,
        "to_role": body.to_role or "physiotherapist",
        "to_user_id": body.to_user_id,
        "audio_base64": audio,
        "transcript": transcript,
        "duration_seconds": body.duration_seconds or 0,
        "created_at": _now(),
    }
    db["voice_messages"].append(item)
    if len(db["voice_messages"]) > 80:
        db["voice_messages"] = db["voice_messages"][-80:]
    save_db(db)
    roles = list({body.to_role, user.role, "doctor", "physiotherapist", "patient"} & {"doctor", "physiotherapist", "patient", "admin"})
    await manager.broadcast_roles(roles, {
        "event": "voice_message",
        "data": {k: v for k, v in item.items() if k != "audio_base64"},
        "message": f"Message from {user.role}: {(transcript or 'voice note')[:60]}",
    })
    return {k: v for k, v in item.items() if k != "audio_base64"}


@app.get("/api/voice-messages/{msg_id}/audio")
async def get_voice_audio(msg_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    m = next((x for x in db.get("voice_messages", []) if x["id"] == msg_id), None)
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    allowed = (
        m.get("from_id") == user.user_id
        or m.get("to_user_id") == user.user_id
        or m.get("to_role") == user.role
        or user.role == "admin"
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not allowed")
    audio = m.get("audio_base64")
    if not audio:
        raise HTTPException(status_code=404, detail="No audio on this message")
    return {"id": msg_id, "audio_base64": audio, "mime": "audio/webm"}


# ---------- Progress evaluation ----------
@app.get("/api/patients/{patient_id}/evaluation")
async def progress_evaluation(patient_id: str, user: TokenData = Depends(get_current_user)):
    db = get_db()
    patient = next((p for p in db["patients"] if p["id"] == patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    sessions = [s for s in db["sessions"] if s["patient_id"] == patient_id]
    sessions.sort(key=lambda x: x.get("created_at", ""))
    if not sessions:
        return {
            "patient_id": patient_id,
            "evaluation": "Insufficient data",
            "score": 0,
            "rom_improvement": 0,
            "pain_trend": "unknown",
            "adherence": patient.get("adherence_percent", 0),
            "recommendations": ["Complete more exercise sessions for evaluation."],
            "session_count": 0,
        }
    first_rom = sessions[0].get("max_rom") or 0
    last_rom = sessions[-1].get("max_rom") or 0
    first_pain = sessions[0].get("pain_score", 5)
    last_pain = sessions[-1].get("pain_score", 5)
    good_q = sum(1 for s in sessions if s.get("quality") == "Good")
    rom_imp = last_rom - first_rom
    pain_delta = first_pain - last_pain  # positive = improvement
    adherence = patient.get("adherence_percent", 0)
    # simple score 0-100
    score = min(100, max(0, int(
        adherence * 0.4 +
        min(40, max(0, rom_imp) * 2) +
        min(20, max(0, pain_delta) * 5) +
        (good_q / max(len(sessions), 1)) * 20
    )))
    if score >= 75:
        evaluation = "Excellent progress"
    elif score >= 55:
        evaluation = "Good progress"
    elif score >= 35:
        evaluation = "Moderate progress – continue plan"
    else:
        evaluation = "Limited progress – review recommended"
    recs = []
    if rom_imp < 5:
        recs.append("ROM gains are small; consider adjusting exercise intensity.")
    if last_pain >= 6:
        recs.append("Pain remains elevated; clinical review advised.")
    if adherence < 60:
        recs.append("Improve session adherence.")
    if good_q / max(len(sessions), 1) < 0.5:
        recs.append("Focus on movement quality; reduce compensation.")
    if not recs:
        recs.append("Maintain current plan and reassess in 1–2 weeks.")
    return {
        "patient_id": patient_id,
        "evaluation": evaluation,
        "score": score,
        "rom_improvement": round(rom_imp, 1),
        "pain_trend": "improving" if pain_delta > 0 else ("worsening" if pain_delta < 0 else "stable"),
        "adherence": adherence,
        "session_count": len(sessions),
        "good_quality_ratio": round(good_q / len(sessions), 2),
        "recommendations": recs,
    }



# ---------- HTML pages ----------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/doctor", response_class=HTMLResponse)
async def doctor_portal(request: Request):
    return templates.TemplateResponse(request, "doctor.html")


@app.get("/physio", response_class=HTMLResponse)
async def physio_portal(request: Request):
    return templates.TemplateResponse(request, "physio.html")


@app.get("/patient", response_class=HTMLResponse)
async def patient_portal(request: Request):
    return templates.TemplateResponse(request, "patient.html")


@app.get("/patient/exercise", response_class=HTMLResponse)
async def exercise_page(request: Request):
    return templates.TemplateResponse(request, "exercise.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_portal(request: Request):
    return templates.TemplateResponse(request, "admin.html")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "PhysioFlex", "version": "1.1.0"}
