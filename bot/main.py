"""
Villa4You WhatsApp Chatbot  —  Level 3 Lead Qualifier & Bookings Assistant

Run:
  uvicorn bot.main:app --reload

Test locally (no Meta needed):
  python bot/main.py chat
  python bot/main.py chat --user Bilal
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "villa4you_verify_2026")
PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN", "")
LLM_API_URL = os.getenv("LLM_API_URL", "https://openrouter.ai/api/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

app = FastAPI(title="Villa4You Chatbot")

# ──────────────────────────────────────────────────────────────
# Villa Knowledge Base
# ──────────────────────────────────────────────────────────────
VILLAS = [
    {
        "id": "putra_6",
        "name": "Putra 6 Villa",
        "badge": "Most Popular",
        "rating": 4.95,
        "location": "Bangi",
        "max_guests": 44,
        "rooms": 17,
        "amenities": ["Private pool", "Optional ballroom", "BBQ area"],
        "price_from": 2500,
        "best_for": ["Large family reunions", "Weddings", "Corporate events", "Birthday parties"],
    },
    {
        "id": "rimba_7",
        "name": "Rimba 7 Villa",
        "badge": "Top Rated",
        "rating": 4.97,
        "location": "Kajang",
        "max_guests": 38,
        "rooms": 9,
        "amenities": ["Private pool", "Optional ballroom", "Event hall"],
        "price_from": 2500,
        "best_for": ["Corporate retreats", "Intimate weddings", "Team building"],
    },
    {
        "id": "nadi_7",
        "name": "Villa Nadi 7",
        "badge": "44 Pax",
        "rating": 4.96,
        "location": "Kajang",
        "max_guests": 44,
        "rooms": 11,
        "amenities": ["Private pool", "Prayer room"],
        "price_from": 2500,
        "best_for": ["Family gatherings", "Religious celebrations", "Group getaways"],
    },
    {
        "id": "sima_6",
        "name": "Villa Sima 6",
        "badge": "Group Favourite",
        "rating": 4.96,
        "location": "Bangi",
        "max_guests": 42,
        "rooms": 13,
        "amenities": ["Private pool", "Optional ballroom"],
        "price_from": 2500,
        "best_for": ["Birthday parties", "Family weekends", "Friends getaways"],
    },
    {
        "id": "one_5",
        "name": "One 5 Residence",
        "badge": "Best Value",
        "rating": 4.93,
        "location": "Puchong",
        "max_guests": 38,
        "rooms": 15,
        "amenities": ["Private pool", "Garden"],
        "price_from": 1800,
        "best_for": ["Budget-conscious groups", "Casual gatherings", "Retreats"],
    },
    {
        "id": "the_1",
        "name": "The 1 Villa",
        "badge": "Cosy & Intimate",
        "rating": 4.99,
        "location": "Puchong",
        "max_guests": 29,
        "rooms": 10,
        "amenities": ["Private pool", "BBQ area"],
        "price_from": 1600,
        "best_for": ["Intimate celebrations", "Small corporate events", "Weekend getaways"],
    },
]

BUSINESS = {
    "name": "Villa4You",
    "phone": "+60 13-500 1515",
    "email": "hello@villa4you.my",
    "locations": ["Bangi", "Puchong", "Kajang"],
    "hours": {
        "Mon-Fri": "9am – 10pm",
        "Saturday": "9am – 11pm",
        "Sunday": "10am – 9pm",
        "Holidays": "10am – 8pm",
    },
    "policies": {
        "min_guests": 20,
        "checkin": "3:00 PM",
        "checkout": "12:00 PM noon",
        "cancellation": "14+ days: 100% refund | 7-13 days: 50% refund | <7 days: non-refundable",
        "payment": "Bank transfer (DuitNow / IBG)",
        "deposit": "Refundable deposit required; returned within 3 business days after checkout",
    },
    "highlights": [
        "6 exclusive private villas",
        "20 to 50+ guests capacity",
        "4.9★ Google Reviews",
        "500+ happy groups",
        "195+ events hosted",
        "100% private bookings",
        "Private pool at every villa",
    ],
}

# ──────────────────────────────────────────────────────────────
# Conversation State
# ──────────────────────────────────────────────────────────────
@dataclass
class Session:
    user_id: str
    state: str = "greeting"  # greeting → collecting → recommendations → handoff
    name: Optional[str] = None
    guests: Optional[int] = None
    dates: Optional[str] = None
    location_pref: Optional[str] = None
    villa_interest: Optional[list[str]] = field(default_factory=list)
    lead_score: int = 0
    turn_count: int = 0
    last_bot_msg: str = ""


sessions: dict[str, Session] = {}

# ──────────────────────────────────────────────────────────────
# LLM helper
# ──────────────────────────────────────────────────────────────

def _system_prompt() -> str:
    return textwrap.dedent("""
    You are a friendly WhatsApp assistant for Villa4You, Malaysia's premier
    group villa rental platform in the Klang Valley.

    Business rules
    -1
    - Always get check-in date, number of guests, and preferred location before recommending villas.
    - If the user didn't give a date, politely ask.
    - If guests < 20, say the minimum is 20 guests.
    - If guests > 50, gently suggest splitting into multiple villas.
    - Mention only real villa names, ratings, prices and locations from the knowledge base.
    - Tone: warm, concise, slightly Wawasan 2020.

    Output rules
    - Return SHORT messages only (<= 280 words).
    - Use 2-3 sentences max unless tables/options are requested.
    - For lists, use short bullet lines.
    - Never mention you are an AI model.
    - If you don't know, say you'll connect them to the team.
    """).strip()


def _villa_context() -> str:
    lines = ["Available villas:"]
    for v in VILLAS:
        lines.append(
            f"- {v['name']} ({v['badge']}) | {v['location']} | "
            f"Up to {v['max_guests']} pax | RM {v['price_from']:,}+/night | "
            f"{', '.join(v['amenities'])}"
        )
    return "\n".join(lines)


async def _call_llm(messages: list[dict]) -> tuple[str, bool]:
    """Call LLM; returns (text, used_llm). Falls back to rules if no key."""
    if not LLM_API_KEY:
        return _rule_based_reply(messages[-1]["content"]), False

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": f"{_system_prompt()}\n\n{_villa_context()}"},
            *messages,
        ],
        "max_tokens": 512,
        "temperature": 0.7,
    }

    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(LLM_API_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip(), True


def _rule_based_reply(user_msg: str) -> str:
    msg = user_msg.lower()
    lower = f" {msg} "

    if any(k in lower for k in ["price", "cost", "rate", "rm ", "budget"]):
        return (
            f"Our villas start from RM {BUSINESS['highlights'][0]} and prices vary by "
            f"villa and season. To quote accurately I need:\n"
            f"1. Check-in date\n2. Number of guests\n3. Preferred location (Bangi / Puchong / Kajang)\n\n"
            f"Share those and I'll shortlist the best fit."
        )
    if any(k in lower for k in ["pool", "swim"]):
        return "Every Villa4You property has a private pool included — no sharing with other guests."
    if any(k in lower for k in ["ballroom", "hall", "event"]):
        return (
            "Ballrooms / event halls are available at Putra 6, Rimba 7 and Villa Sima 6. "
            "Pick your location and I'll confirm details."
        )
    if any(k in lower for k in ["prayer", "musolla", "surau"]):
        return "Villa Nadi 7 in Kajang includes a dedicated prayer room. Would you like details?"
    if any(k in lower for k in ["cancel", "refund", "policy"]):
        return (
            f"Cancellation policy:\n{BUSINESS['policies']['cancellation']}\n"
            "For emergencies, message us directly and we'll see what we can do."
        )
    if any(k in lower for k in ["book", "reserve", "availability", "check", "date"]):
        return (
            "To check availability, I need your check-in date, number of guests and preferred location. "
            "Send those three and I'll verify for you."
        )
    if any(k in lower for k in ["pet", "dog", "cat"]):
        return "Pets are strictly not allowed at all properties to keep every guest's stay comfortable."
    if any(k in lower for k in ["smoke", "vape", "cigarette"]):
        return "No smoking inside any villa. Designated outdoor areas are provided; indoor smoking incurs a cleaning fee."
    if any(k in lower for k in ["thank", "thanks", "great", "perfect"]):
        return "You're welcome! Need anything else — dates, villa pick, or pricing — just ask."

    return (
        "I can help with villa recommendations, pricing, availability, and booking. "
        "Tell me your check-in date, number of guests and preferred location and I'll get started."
    )


# ──────────────────────────────────────────────────────────────
# Lead scoring & villa matching
# ──────────────────────────────────────────────────────────────
def _score_lead(session: Session) -> int:
    score = 0
    if session.name:
        score += 25
    if session.guests and session.guests >= 20:
        score += 35
    if session.dates:
        score += 20
    if session.location_pref:
        score += 15
    if session.villa_interest:
        score += 5
    return min(score, 100)


def _match_villas(session: Session) -> list[dict]:
    pool = VILLAS[:]
    if session.location_pref:
        pool = [v for v in pool if v["location"].lower() == session.location_pref.lower()]
    if session.guests:
        pool = [v for v in pool if v["max_guests"] >= session.guests]
    # Sort by rating desc then price asc
    pool.sort(key=lambda v: (-v["rating"], v["price_from"]))
    return pool[:3]


def _handoff_msg(session: Session) -> str:
    pct = session.lead_score
    if pct >= 75:
        return (
            "I have enough to connect you to the team now. "
            f"They respond within a few hours on WhatsApp: {BUSINESS['phone']}\n\n"
            "Mention: your name, guest count, dates and which villa you're eyeing."
        )
    if pct >= 40:
        return (
            "To speed things up, tell me:\n"
            "• Your check-in date\n"
            "• Exact guest count\n"
            "• Preferred location (Bangi / Puchong / Kajang)\n\n"
            "Our team replies fast on WhatsApp."
        )
    return (
        "For custom quotes and availability, WhatsApp our team at "
        f"{BUSINESS['phone']} — they're online Mon-Fri 9am-10pm, Sat 9am-11pm, Sun 10am-9pm."
    )


# ──────────────────────────────────────────────────────────────
# Reply builder — primary orchestration logic
# ──────────────────────────────────────────────────────────────
async def get_reply(user_id: str, user_msg: str) -> str:
    session = sessions.setdefault(user_id, Session(user_id=user_id))
    session.turn_count += 1

    # Extract structured data from free-text message (lightweight)
    m = re.search(r"(\d{1,2})\s*(?:pax|guest|people|person)", user_msg, re.I)
    if m:
        n = int(m.group(1))
        session.guests = max(session.guests or 0, n)
        if n < BUSINESS["policies"]["min_guests"]:
            session.guests = BUSINESS["policies"]["min_guests"]

    m = re.search(r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{0,4}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\s*\d{0,4}|\d{4}-\d{2}-\d{2})", user_msg, re.I)
    if m:
        session.dates = m.group(0)

    for loc in BUSINESS["locations"]:
        if loc.lower() in user_msg.lower():
            session.location_pref = loc

    for v in VILLAS:
        if v["name"].split()[0].lower() in user_msg.lower() or v["id"].replace("_", " ").lower() in user_msg.lower():
            session.villa_interest.append(v["id"])

    if not session.name:
        m = re.search(r"\b(?:i'm|im|my name is|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", user_msg)
        if m:
            session.name = m.group(1).title()

    # Greeting / restart
    session.lead_score = _score_lead(session)

    # Build conversation history for LLM
    history = [
        {"role": "user", "content": user_msg}
    ]
    if session.state == "greeting" or session.turn_count == 1:
        history[0]["content"] = f"User just messaged: {user_msg}"

    # Try LLM first
    reply, used = await _call_llm(history)

    already_handed_off = getattr(session, "_handed_off", False)
    lower_msg = user_msg.lower()

    if session.state == "greeting" or session.turn_count == 1:
        reply = (
            "Welcome to Villa4You! 🏡\n"
            "We have 6 private villas in Bangi, Puchong & Kajang.\n"
            "Tell me:\n"
            "1. Check-in date\n2. Guest count (min 20)\n3. Preferred location\n\n"
            "I'll shortlist the perfect villa for your group."
        )
        session.state = "collecting"
    elif session.lead_score >= 75 and not already_handed_off and not used:
        reply = reply + "\n\n" + _handoff_msg(session)
        session._handed_off = True
        session.state = "handoff"
    elif session.lead_score >= 40 and session.turn_count >= 6 and not already_handed_off and not used:
        reply = _handoff_msg(session)
        session._handed_off = True
        session.state = "handoff"
    elif not used and session.lead_score >= 10 and any(k in lower_msg for k in ["recommend", "suggest", "which", "best", "shortlist"]):
        matches = _match_villas(session)
        if not matches:
            reply = "To give you the best shortlist, tell me your check-in date, guest count and preferred location — that way I can accurately match your group."
        else:
            lines = ["Here are the best fits right now:\n"]
            for i, v in enumerate(matches, 1):
                lines.append(
                    f"{i}. *{v['name']}* ({v['badge']}) — {v['location']}\n"
                    f"   • {v['max_guests']} guests | RM {v['price_from']:,}+/night\n"
                    f"   • {', '.join(v['amenities'])}\n"
                )
            lines.append("\nWant exact pricing and availability? Share your dates.")
            reply = "\n".join(lines)
            session.state = "recommendations"
    elif not used and session.lead_score >= 10:
        missing = []
        if not session.dates:
            missing.append("check-in date")
        if not session.location_pref:
            missing.append("preferred location (Bangi / Puchong / Kajang)")
        if session.guests and session.guests < BUSINESS["policies"]["min_guests"]:
            missing.append(f"note: minimum is {BUSINESS['policies']['min_guests']} guests")
        if missing:
            reply = (
                "Got it. To finish matching, I still need:\n"
                + "\n".join(f"• {m}" for m in missing[:3])
                + "\n\nOnce I have those I can shortlist the best villa and price."
            )
        else:
            reply = "Thanks for that! If you have a specific villa in mind or want me to shortlist based on your dates and guest count, just say the word."

    if already_handed_off and not used and not lower_msg.startswith("thanks"):
        reply = "Our team will be with you shortly on WhatsApp. Anything else you'd like me to add before they connect?"

    session.last_bot_msg = reply
    return reply


# ──────────────────────────────────────────────────────────────
# WhatsApp webhook endpoints
# ──────────────────────────────────────────────────────────────
class WhatsAppMessage(BaseModel):
    object: str
    entry: list


@app.get("/webhook/whatsapp")
async def verify_webhook(mode: str = None, token: str = None, challenge: str = None, hub_verify_token: str = None):
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def receive_webhook(payload: WhatsAppMessage):
    if payload.object != "whatsapp_business_account":
        return JSONResponse({"status": "ignored"}, status_code=200)

    try:
        change = payload.entry[0]["changes"][0]["value"]
        if "messages" not in change:
            return JSONResponse({"status": "no messages"}, status_code=200)

        message = change["messages"][0]
        sender = message["from"]
        text = ""

        if message["type"] == "text":
            text = message["text"]["body"]
        else:
            # Basic interactive support
            text = message.get("interactive", {}).get("button_reply", {}).get("title", "")

        if not text:
            return JSONResponse({"status": "no text"}, status_code=200)

        reply = await get_reply(sender, text)
        await send_whatsapp(sender, reply)
        return JSONResponse({"status": "ok"}, status_code=200)

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def send_whatsapp(to: str, text: str):
    """Send WhatsApp message via Cloud API."""
    if not (PHONE_NUMBER_ID and ACCESS_TOKEN):
        return  # offline mode

    import httpx
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(url, headers=headers, json=payload)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────
# Local CLI chat simulator
# ──────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html><body style="font-family: system-ui; max-width: 480px; margin: 40px auto; padding: 0 20px;">
<h2>Villa4You Chatbot</h2>
<p>Webhook listening at <code>/webhook/whatsapp</code></p>
<p>Simulator: <code>python bot/main.py chat</code></p>
<p>Status: <strong>running</strong></p>
</body></html>"""


def _cli_chat_once(user_id: str, message: str):
    import asyncio
    return asyncio.run(get_reply(user_id, message))


def run_cli_chat(user_id: str = "cli-user"):
    print("Villa4You Chatbot — local simulator")
    print("Type 'quit' to exit\n")
    while True:
        msg = input("You: ").strip()
        if msg.lower() in {"quit", "exit"}:
            break
        if not msg:
            continue
        reply = _cli_chat_once(user_id, msg)
        print(f"Bot: {reply}\n")


# ──────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "chat":
        run_cli_chat(sys.argv[2] if len(sys.argv) > 2 else "local-user")
    else:
        uvicorn.run("bot.main:app", host="0.0.0.0", port=8000, reload=True)
