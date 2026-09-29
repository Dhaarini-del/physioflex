"""One-time migration of the prototype data/db.json into MongoDB Atlas.
Run locally after setting MONGODB_URI.
"""
import os
from pathlib import Path
from pymongo import MongoClient

BASE_DIR = Path(__file__).resolve().parent
SOURCE = BASE_DIR / "data" / "db.json"
COLLECTIONS = [
    "users", "patients", "assessments", "rehab_plans", "exercises", "sessions",
    "notes", "alerts", "events", "complaints", "voice_messages", "bookings",
    "patient_alerts", "suggestions", "schedules", "credential_requests",
]

if not os.getenv("MONGODB_URI"):
    raise SystemExit("Set MONGODB_URI before running this migration.")

import json
with SOURCE.open("r", encoding="utf-8") as f:
    data = json.load(f)

client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=10000)
client.admin.command("ping")
db = client[os.getenv("MONGO_DB_NAME", "physioflex")]

for name in COLLECTIONS:
    coll = db[name]
    coll.delete_many({})
    rows = data.get(name, [])
    if rows:
        coll.insert_many(rows, ordered=False)
    print(f"{name}: {len(rows)} records")

print("Migration complete.")
