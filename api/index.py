import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, String, Text, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

app = FastAPI(title="Retirement Rhythm")

GOOGLE_SEARCH_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
SYSTEM_PROMPT = """Du entwirfst freundliche, aktivierende und realistische Tagespläne auf Deutsch für Menschen in ihren 80ern in der Schweiz.
Nutze nur die vom Nutzer angegebenen persönlichen Angaben und öffentlich passende lokale Kontexte. Erfinde keine privaten persönlichen Details und grabe nicht nach sensiblen Informationen.
Berücksichtige ausdrücklich das gewählte Aktivitätsgefühl des Tages. Wenn sich jemand heute jünger, energievoller und unternehmungslustiger fühlt, darf der Plan lebendiger, aktiver und abwechslunsgreicher sein. Wenn sich jemand heute ruhiger fühlt, soll der Plan sanfter, langsamer und entlastender sein.
Return valid JSON with keys:
headline: string,
summary: string,
rhythm: array of 4 to 7 objects with keys time, title, note,
activity_ideas: array of 4 to 6 short strings,
safety_notes: array of 2 to 4 short strings.
Alles auf Deutsch, warm, praktisch und konkret.
"""


class Base(DeclarativeBase):
    pass


class SavedPlan(Base):
    __tablename__ = "retirement_day_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    person_name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120))
    headline: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str] = mapped_column(Text())
    plan_json: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavePlanPayload(BaseModel):
    personName: str = Field(..., min_length=1, max_length=120)
    location: str = Field(..., min_length=1, max_length=120)
    headline: str = Field(..., min_length=1, max_length=240)
    summary: str = Field(..., min_length=1)
    plan: Dict[str, Any]


def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing {name}")
    return value


def get_session_factory():
    engine = create_async_engine(get_required_env("DATABASE_URL"), pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False), engine


@app.on_event("startup")
async def startup() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    session_factory, engine = get_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "hasOpenAI": bool(os.getenv("OPENAI_API_KEY")),
        "hasGoogle": bool(os.getenv("GOOGLE_API_KEY")),
        "hasDatabase": bool(os.getenv("DATABASE_URL")),
    }


@app.get("/api/demo")
async def demo() -> Dict[str, Any]:
    return await build_plan("Susanne Schär", "Münchenstein", "Sanfte Aktivierung, soziale Kontakte, kleine Wege ausser Haus und ein ruhiger, strukturierter Tagesfluss", "Heute eher jung und unternehmungslustig")


@app.get("/api/plan")
async def plan(person: str, location: str = "Münchenstein", focus: str = "Den Tag freundlich, aktivierend und realistisch strukturieren", vibe: str = "Ausgeglichen und locker") -> Dict[str, Any]:
    return await build_plan(person.strip(), location.strip(), focus.strip(), vibe.strip())


@app.get("/api/saved-plans")
async def saved_plans() -> Dict[str, Any]:
    session_factory, engine = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(SavedPlan).order_by(SavedPlan.created_at.desc()).limit(20))
        items = result.scalars().all()
    await engine.dispose()
    return {
        "items": [
            {
                "id": item.id,
                "personName": item.person_name,
                "location": item.location,
                "headline": item.headline,
                "summary": item.summary,
                "plan": json.loads(item.plan_json),
                "createdAt": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ]
    }


@app.post("/api/saved-plans")
async def save_plan(payload: SavePlanPayload) -> Dict[str, Any]:
    session_factory, engine = get_session_factory()
    record = SavedPlan(
        id=str(uuid4()),
        person_name=payload.personName.strip(),
        location=payload.location.strip(),
        headline=payload.headline.strip(),
        summary=payload.summary.strip(),
        plan_json=json.dumps(payload.plan),
        created_at=datetime.now(timezone.utc),
    )
    async with session_factory() as session:
        session.add(record)
        await session.commit()
    await engine.dispose()
    return {"ok": True, "id": record.id}


async def build_plan(person: str, location: str, focus: str, vibe: str) -> Dict[str, Any]:
    google_key = get_required_env("GOOGLE_API_KEY")
    openai_key = get_required_env("OPENAI_API_KEY")
    research = await swiss_activity_research(location, focus, google_key)
    plan = await generate_plan(person, location, focus, vibe, research, openai_key)
    return {"person": person, "location": location, "focus": focus, "vibe": vibe, "research": research, "plan": plan}


async def swiss_activity_research(location: str, focus: str, api_key: str) -> Dict[str, Any]:
    prompt = (
        f"Suche im Web nach sanften, realistischen Aktivitäten, Ausflugsideen, Gemeinschaftsangeboten, Seniorinnen- und Seniorenprogrammen, "
        f"mobilitätsfreundlichen Möglichkeiten und saisonalen Routinen für Menschen in ihren 80ern in der Schweiz, mit Schwerpunkt auf {location}. "
        f"Ergänze nur öffentlich naheliegende lokale Kontexte, keine privaten persönlichen Details. Fokus: {focus}. Antworte auf Deutsch."
    )
    payload = {"tools": [{"google_search": {}}], "contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{GOOGLE_SEARCH_URL}?key={api_key}",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Google search failed: {response.text[:400]}")
    data = response.json()
    return {"summary": extract_gemini_text(data), "sources": extract_gemini_sources(data)[:8]}


async def generate_plan(person: str, location: str, focus: str, vibe: str, research: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    source_lines = "\n".join(f"- {item.get('title', 'Untitled')}: {item.get('url', '')}" for item in research.get("sources", []))
    payload = {
        "model": "gpt-4.1-mini",
        "text": {
            "format": {
                "type": "json_schema",
                "name": "retirement_plan",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "headline": {"type": "string"},
                        "summary": {"type": "string"},
                        "rhythm": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "time": {"type": "string"},
                                    "title": {"type": "string"},
                                    "note": {"type": "string"}
                                },
                                "required": ["time", "title", "note"]
                            }
                        },
                        "activity_ideas": {"type": "array", "items": {"type": "string"}},
                        "safety_notes": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["headline", "summary", "rhythm", "activity_ideas", "safety_notes"]
                }
            }
        },
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Person: {person}\nOrt: {location}\nFokus: {focus}\nTagesgefühl / Aktivitätsniveau: {vibe}\n\nÖffentlich passender Kontext: Die Person heisst Susanne Schär und lebt in Münchenstein. Personalisierung nur auf Basis dieses Namens, des Orts und der öffentlich sinnvollen lokalen Möglichkeiten. Keine privaten Behauptungen erfinden.\n\nRecherchezusammenfassung:\n{research.get('summary', '')}\n\nQuellen:\n{source_lines}\n\nGib nur JSON zurück, aber in deutscher Sprache.",
            },
        ],
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenAI call failed: {response.text[:400]}")
    data = response.json()
    text = extract_openai_text(data)
    return json.loads(text)


def extract_gemini_text(data: Dict[str, Any]) -> str:
    texts: List[str] = []
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def extract_gemini_sources(data: Dict[str, Any]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    for candidate in data.get("candidates", []):
        meta = candidate.get("groundingMetadata", {})
        for chunk in meta.get("groundingChunks", []):
            web = chunk.get("web") or {}
            url = web.get("uri")
            title = web.get("title")
            if url and url not in seen:
                out.append({"title": title or url, "url": url})
                seen.add(url)
    return out


def extract_openai_text(data: Dict[str, Any]) -> str:
    parts: List[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "\n".join(parts).strip() or data.get("output_text", "").strip()


@app.exception_handler(HTTPException)
async def http_exception_handler(_, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})
