
# chat_routes.py
import os
import json
import asyncio
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi import Request as FastAPIRequest
from pydantic import BaseModel, Field

from main import (
    TokenData,
    get_current_user,
    get_db,
    _can_access_patient,
)

router = APIRouter()


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    patient_id: Optional[str] = None


def get_collection(db, name):
    """Support a dict-style JSON database."""
    if isinstance(db, dict):
        return db.get(name, [])
    return []


def find_patient_context(user: TokenData, patient_id: Optional[str], db):
    patients = get_collection(db, "patients")

    # Patients can only access their own record.
    if user.role == "patient":
        patient = next(
            (
                p for p in patients
                if p.get("user_id") == user.user_id
                or p.get("id") == user.user_id
            ),
            None,
        )
        return patient

    # Clinicians must explicitly select a patient they are allowed to access.
    if user.role in ("doctor", "physiotherapist"):
        if not patient_id:
            return None

        patient = next(
            (p for p in patients if str(p.get("id")) == str(patient_id)),
            None,
        )
        if patient and _can_access_patient(user, patient):
            return patient

        raise HTTPException(
            status_code=403,
            detail="You do not have access to this patient's information.",
        )

    # Admin can use general chatbot support, without patient medical records.
    return None


def build_context(patient, db):
    if not patient:
        return "No patient medical record has been provided. Give general information only."

    patient_id = str(patient.get("id", ""))
    context = {
        "patient": {
            "id": patient_id,
            "name": patient.get("name"),
            "injury": patient.get("injury"),
            "condition": patient.get("condition"),
            "recovery_stage": patient.get("recovery_stage"),
            "pain_level": patient.get("pain_level"),
        },
        "sessions": [
            item for item in get_collection(db, "sessions")
            if str(item.get("patient_id")) == patient_id
        ][-5:],
        "assessments": [
            item for item in get_collection(db, "assessments")
            if str(item.get("patient_id")) == patient_id
        ][-5:],
        "rehab_plans": [
            item for item in get_collection(db, "rehab_plans")
            if str(item.get("patient_id")) == patient_id
        ][-3:],
        "alerts": [
            item for item in get_collection(db, "patient_alerts")
            if str(item.get("patient_id")) == patient_id
        ][-5:],
    }
    return json.dumps(context, default=str)[:12000]


def gemini_request(message, role, context):
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    if not api_key:
        return (
            "The AI assistant is not configured yet. Please set the "
            "GEMINI_API_KEY environment variable on your backend. "
            "For medical concerns, contact your healthcare professional."
        )

    prompt = f"""
You are PhysioFlex Smart Chat, an assistant for a rehabilitation platform.

Current portal role: {role}
Authorized patient context, if provided: {context}

Guidelines:
- Be supportive, clear, and concise.
- Give general physiotherapy education, not a definitive diagnosis.
- Do not invent patient measurements or treatment history.
- Do not prescribe medication or change a clinician's treatment plan.
- Encourage users to follow their clinician-approved rehabilitation plan.
- If pain is severe, sudden, worsening, or accompanied by alarming symptoms,
  recommend stopping the exercise and seeking prompt professional assessment.
- If the user describes an emergency, advise contacting local emergency services.
- Do not claim to have sent alerts or changed records unless the backend did so.
- Respect the user's role and only discuss the patient context supplied to you.

User message: {message}
"""

    payload = json.dumps({
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 700
        }
    }).encode("utf-8")

    req = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, ValueError):
        return (
            "Sorry, I couldn't reach the AI assistant right now. Please try "
            "again later. If you have worsening pain or a medical concern, "
            "contact your doctor or physiotherapist."
        )


@router.get("/chat", response_class=HTMLResponse)
async def chat_page():
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    # This endpoint is protected by the message API's authentication.
    # Your existing login flow should be used to access the chat page.
    return HTMLResponse(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>PhysioFlex Smart Chat</title></head>'
        '<body><script>window.location.href="/login";</script>'
        '<p>Please sign in to continue.</p></body></html>'
    )


@router.post("/api/chat/message")
async def send_chat_message(
    body: ChatMessage,
    user: TokenData = Depends(get_current_user),
):
    db = get_db()
    patient = find_patient_context(user, body.patient_id, db)
    context = build_context(patient, db)

    reply = await asyncio.to_thread(
        gemini_request, body.message, user.role, context
    )

    return {
        "reply": reply,
        "role": user.role,
        "patient_context_available": patient is not None,
    }
