"""PhysioFlex persistence layer.

Uses MongoDB Atlas in deployed environments and falls back to the bundled JSON
file for local development when MONGODB_URI is not configured.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    from pymongo import MongoClient
except ImportError:  # pragma: no cover
    MongoClient = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "db.json"
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "physioflex")
_lock = threading.Lock()
_client = None
_mongo_db = None

COLLECTIONS = [
    "users", "patients", "assessments", "rehab_plans", "exercises", "sessions",
    "notes", "alerts", "events", "complaints", "voice_messages", "bookings",
    "patient_alerts", "suggestions", "schedules", "credential_requests",
]

DATASET_EXERCISES = [
    {"id": "e1", "name": "Extended Leg Raises", "body_part": "Hip / Knee", "joints": ["right_hip", "right_knee"],
     "description": "Lying supine, raise the extended leg upward. Dataset e1.", "dataset_code": "e1", "default_sets": 3, "default_reps": 10, "default_target_rom": 45},
    {"id": "e2", "name": "Forward Bending", "body_part": "Spine / Hip", "joints": ["spine", "hip"],
     "description": "Standing or seated forward bend. Dataset e2.", "dataset_code": "e2", "default_sets": 3, "default_reps": 10, "default_target_rom": 90},
    {"id": "e3", "name": "Straight Lying-Leg Raises", "body_part": "Hip / Knee", "joints": ["right_hip", "right_knee"],
     "description": "Supine straight-leg raise (SLR). Dataset e3.", "dataset_code": "e3", "default_sets": 3, "default_reps": 12, "default_target_rom": 60},
    {"id": "e4", "name": "Side Lying Hip Abduction", "body_part": "Hip", "joints": ["right_hip"],
     "description": "Side-lying hip abduction. Dataset e4.", "dataset_code": "e4", "default_sets": 3, "default_reps": 12, "default_target_rom": 40},
    {"id": "e5", "name": "Alternating Leg Lifts Prone", "body_part": "Hip / Lumbar", "joints": ["hip", "spine"],
     "description": "Prone alternating leg lifts. Dataset e5.", "dataset_code": "e5", "default_sets": 3, "default_reps": 10, "default_target_rom": 30},
    {"id": "e6", "name": "Elbow Flexion", "body_part": "Elbow", "joints": ["right_elbow"],
     "description": "Elbow flexion PT exercise. Dataset e6.", "dataset_code": "e6", "default_sets": 3, "default_reps": 15, "default_target_rom": 140},
    {"id": "e7", "name": "Shoulder Abduction", "body_part": "Shoulder", "joints": ["right_shoulder"],
     "description": "Shoulder abduction. Dataset e7.", "dataset_code": "e7", "default_sets": 3, "default_reps": 12, "default_target_rom": 160},
    {"id": "e8", "name": "Prone Lying Elbow Extension", "body_part": "Elbow", "joints": ["right_elbow"],
     "description": "Prone elbow extension. Dataset e8.", "dataset_code": "e8", "default_sets": 3, "default_reps": 12, "default_target_rom": 0},
    {"id": "ex001", "name": "Seated Knee Extension", "body_part": "Knee", "joints": ["right_knee"],
     "description": "Seated open-chain knee extension for quadriceps and ROM.", "dataset_code": None, "default_sets": 3, "default_reps": 12, "default_target_rom": 120},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_db() -> Dict[str, Any]:
    return {key: [] for key in COLLECTIONS}


def _local_load() -> Dict[str, Any]:
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = _empty_db()
        data["exercises"] = DATASET_EXERCISES
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data
    with open(DB_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key in COLLECTIONS:
        data.setdefault(key, [])
    return data


def _local_save(data: Dict[str, Any]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_mongo_db():
    global _client, _mongo_db
    if not MONGODB_URI:
        return None
    if MongoClient is None:
        raise RuntimeError("pymongo is required when MONGODB_URI is configured")
    if _mongo_db is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000)
        _mongo_db = _client[MONGO_DB_NAME]
        _client.admin.command("ping")
    return _mongo_db


def _mongo_load() -> Dict[str, Any]:
    db = _get_mongo_db()
    data = _empty_db()
    for collection in COLLECTIONS:
        data[collection] = list(db[collection].find({}, {"_id": 0}))
    return data


def _mongo_save(data: Dict[str, Any]) -> None:
    db = _get_mongo_db()
    for collection in COLLECTIONS:
        coll = db[collection]
        coll.delete_many({})
        rows = data.get(collection) or []
        if rows:
            coll.insert_many(rows, ordered=False)


def get_db() -> Dict[str, Any]:
    with _lock:
        return _mongo_load() if MONGODB_URI else _local_load()


def save_db(data: Dict[str, Any]) -> None:
    with _lock:
        if MONGODB_URI:
            _mongo_save(data)
        else:
            _local_save(data)


def generate_id(prefix: str = "") -> str:
    return (prefix + str(uuid.uuid4())[:8]) if prefix else str(uuid.uuid4())[:8]


def append_event(event_type: str, payload: dict, patient_id: str = None) -> dict:
    data = get_db()
    event = {
        "id": generate_id("ev"),
        "type": event_type,
        "patient_id": patient_id,
        "payload": payload,
        "created_at": _now(),
    }
    data.setdefault("events", []).append(event)
    data["events"] = data["events"][-200:]
    save_db(data)
    return event


def _seed_data() -> Dict[str, Any]:
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd.hash(os.getenv("DEMO_PASSWORD", "password123"))
    data = _empty_db()
    data["users"] = [
        {"id": "adm001", "email": "admin@physioflex.com", "password": hashed, "name": "System Admin", "role": "admin", "created_at": _now()},
        {"id": "doc001", "email": "doctor@physioflex.com", "password": hashed, "name": "Dr. Ananya Sharma", "role": "doctor", "specialty": "Orthopedics", "created_at": _now()},
        {"id": "phy001", "email": "physio@physioflex.com", "password": hashed, "name": "Rahul Mehta", "role": "physiotherapist", "license": "PT-2024-8842", "created_at": _now()},
        {"id": "pat001", "email": "patient@physioflex.com", "password": hashed, "name": "Aarav Patel", "role": "patient", "age": 34, "gender": "Male", "created_at": _now()},
    ]
    data["exercises"] = DATASET_EXERCISES
    data["patients"] = [{
        "id": "pat001", "user_id": "pat001", "name": "Aarav Patel", "age": 34, "gender": "Male",
        "email": "patient@physioflex.com", "condition": "Post-ACL Reconstruction (Right Knee)",
        "summary": "34M post right ACL reconstruction. Progressing through Phase 2 strengthening and ROM.",
        "operation": "Right ACL Reconstruction (hamstring autograft)", "reason_of_operation": "Complete ACL tear after sports injury with instability.",
        "surgery_date": "2026-07-15", "doctor_id": "doc001", "physio_id": "phy001",
        "current_pain": 3, "current_rom": 115, "target_rom": 135, "adherence_percent": 82,
        "status": "active", "created_at": _now(), "updated_at": _now(),
    }]
    data["assessments"] = [{"id": "asm001", "patient_id": "pat001", "physio_id": "phy001", "date": "2026-09-20", "pain_score": 4, "rom_knee_flexion": 110, "rom_knee_extension": 5, "notes": "Mild swelling. Good quadriceps activation.", "created_at": _now()}]
    data["rehab_plans"] = [{
        "id": "plan001", "patient_id": "pat001", "physio_id": "phy001", "title": "ACL Phase 2 – Strength & ROM",
        "start_date": "2026-09-21", "end_date": "2026-10-21", "status": "active",
        "exercises": [
            {"exercise_id": "ex001", "name": "Seated Knee Extension", "sets": 3, "reps": 12, "target_rom": 120, "frequency": "Daily", "instructions": "Sit upright. Slowly extend knee fully. Hold 2s."},
            {"exercise_id": "e3", "name": "Straight Lying-Leg Raises", "sets": 3, "reps": 12, "target_rom": 60, "frequency": "Daily", "instructions": "Lie on back. Keep knee straight. Raise leg. Hold 3s."},
            {"exercise_id": "e1", "name": "Extended Leg Raises", "sets": 3, "reps": 10, "target_rom": 45, "frequency": "Daily", "instructions": "From dataset e1. Raise extended leg controlled."},
        ], "created_at": _now(), "updated_at": _now(),
    }]
    data["sessions"] = [
        {"id": "ses001", "patient_id": "pat001", "plan_id": "plan001", "exercise_id": "ex001", "exercise_name": "Seated Knee Extension", "date": "2026-09-28", "reps_completed": 11, "target_reps": 12, "sets_completed": 3, "max_rom": 118, "avg_rom": 112, "quality": "Good", "pain_score": 3, "duration_seconds": 245, "source": "camera", "created_at": _now()},
        {"id": "ses002", "patient_id": "pat001", "plan_id": "plan001", "exercise_id": "ex001", "exercise_name": "Seated Knee Extension", "date": "2026-09-27", "reps_completed": 12, "target_reps": 12, "sets_completed": 3, "max_rom": 115, "avg_rom": 109, "quality": "Fair", "pain_score": 4, "duration_seconds": 268, "source": "camera", "created_at": _now()},
    ]
    data["notes"] = [{"id": "note001", "patient_id": "pat001", "author_id": "phy001", "author_role": "physiotherapist", "content": "Patient reporting reduced swelling. ROM improving steadily.", "created_at": _now()}]
    data["alerts"] = [{"id": "alt001", "patient_id": "pat001", "type": "movement", "severity": "medium", "message": "Slight compensatory hip hike during knee extension on 2026-09-27.", "resolved": False, "created_at": _now()}]
    return data


def seed_if_empty() -> None:
    data = get_db()
    if data.get("users"):
        data["exercises"] = DATASET_EXERCISES
        changed = False
        for key in COLLECTIONS:
            if key not in data:
                data[key] = []
                changed = True
        if not any(u.get("role") == "admin" for u in data["users"]):
            from passlib.context import CryptContext
            hashed = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(os.getenv("DEMO_PASSWORD", "password123"))
            data["users"].insert(0, {"id": "adm001", "email": "admin@physioflex.com", "password": hashed, "name": "System Admin", "role": "admin", "created_at": _now()})
            changed = True
        save_db(data)
        return
    save_db(_seed_data())
    print("PhysioFlex database seeded")
