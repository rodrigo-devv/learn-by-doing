"""API do Akademía.

Modelo: SEMANAS → ITENS (cada item tem status, tags, vídeo, links, docs, notas).
É essa API que:
  - o site (front-end React) consome para ler e gravar tudo;
  - o servidor MCP chama quando o seu Claude adiciona itens conversando.

Os IDs são inteiros do banco, mas devolvidos como string (ex: "12"), pois o
front-end trata id como string.
"""
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Akademía API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Token de acesso. Se AKADEMIA_TOKEN estiver vazio (padrão local), a auth fica
# DESLIGADA. Em produção, defina a variável de ambiente para proteger a API.
API_TOKEN = os.environ.get("AKADEMIA_TOKEN", "")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Exige o token nas rotas /api/* (exceto health) quando AKADEMIA_TOKEN existe.

    Aceita 'Authorization: Bearer <token>' ou 'X-API-Key: <token>'.
    Requisições OPTIONS (preflight CORS) e o site estático passam livres.
    """
    path = request.url.path
    protegida = path.startswith("/api/") and path != "/api/health"
    if API_TOKEN and protegida and request.method != "OPTIONS":
        auth = request.headers.get("authorization", "")
        bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        provided = bearer or request.headers.get("x-api-key", "")
        if provided != API_TOKEN:
            return JSONResponse({"detail": "Não autorizado"}, status_code=401)
    return await call_next(request)


# ---------- serialização (colunas PT -> chaves do front-end) ----------
def item_dict(it: models.Item) -> dict:
    return {
        "id": str(it.id),
        "title": it.titulo,
        "status": it.status,
        "tags": it.tags or [],
        "video": it.video or "",
        "links": it.links or [],
        "docs": it.docs or [],
        "notes": it.notas or "",
    }


def semana_dict(s: models.Semana) -> dict:
    return {"id": str(s.id), "title": s.titulo, "items": [item_dict(it) for it in s.itens]}


def get_semana_or_404(db: Session, semana_id: int) -> models.Semana:
    obj = db.get(models.Semana, semana_id)
    if not obj:
        raise HTTPException(404, "Semana não encontrada")
    return obj


def get_item_or_404(db: Session, item_id: int) -> models.Item:
    obj = db.get(models.Item, item_id)
    if not obj:
        raise HTTPException(404, "Item não encontrado")
    return obj


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    """Diagnóstico do serviço (livre de autenticação, usado pelo healthcheck).

    Mostra qual banco está ativo, se a conexão funciona, se a auth está ligada,
    a versão e a contagem de dados — útil para confirmar visualmente o estado.
    """
    # 'postgresql' | 'sqlite' -> nome amigável.
    engine_name = "postgres" if engine.dialect.name == "postgresql" else engine.dialect.name
    info = {
        "status": "ok",
        "version": app.version,
        "auth": "enabled" if API_TOKEN else "disabled",
        "db": {"engine": engine_name, "connected": False},
    }
    try:
        info["db"]["counts"] = {
            "semanas": db.query(models.Semana).count(),
            "itens": db.query(models.Item).count(),
        }
        info["db"]["connected"] = True
    except Exception as exc:  # banco inacessível: app de pé, mas degradado
        info["status"] = "degraded"
        info["db"]["error"] = type(exc).__name__
    return info


# ===================== ESTADO COMPLETO =====================
@app.get("/api/state")
def get_state(db: Session = Depends(get_db)):
    """Devolve {weeks: [...]} — usado pelo site no carregamento inicial."""
    semanas = db.scalars(
        select(models.Semana).order_by(models.Semana.ordem, models.Semana.id)
    ).all()
    return {"weeks": [semana_dict(s) for s in semanas]}


# ===================== SEMANAS =====================
@app.post("/api/semanas", status_code=201)
def criar_semana(payload: schemas.SemanaCreate, db: Session = Depends(get_db)):
    proxima_ordem = db.query(models.Semana).count()
    obj = models.Semana(titulo=payload.title, ordem=proxima_ordem)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return semana_dict(obj)


@app.patch("/api/semanas/{semana_id}")
def atualizar_semana(semana_id: int, payload: schemas.SemanaUpdate, db: Session = Depends(get_db)):
    obj = get_semana_or_404(db, semana_id)
    obj.titulo = payload.title
    db.commit()
    db.refresh(obj)
    return semana_dict(obj)


@app.delete("/api/semanas/{semana_id}", status_code=204)
def remover_semana(semana_id: int, db: Session = Depends(get_db)):
    obj = get_semana_or_404(db, semana_id)
    db.delete(obj)
    db.commit()


# ===================== ITENS =====================
@app.post("/api/semanas/{semana_id}/itens", status_code=201)
def criar_item(semana_id: int, payload: schemas.ItemCreate, db: Session = Depends(get_db)):
    get_semana_or_404(db, semana_id)
    proxima_ordem = db.query(models.Item).filter(models.Item.semana_id == semana_id).count()
    obj = models.Item(
        semana_id=semana_id,
        titulo=payload.title,
        status=payload.status,
        tags=payload.tags,
        video=payload.video,
        links=[l.model_dump() for l in payload.links],
        docs=[d.model_dump() for d in payload.docs],
        notas=payload.notes,
        ordem=proxima_ordem,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return item_dict(obj)


@app.patch("/api/itens/{item_id}")
def atualizar_item(item_id: int, payload: schemas.ItemUpdate, db: Session = Depends(get_db)):
    obj = get_item_or_404(db, item_id)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        obj.titulo = data["title"]
    if "status" in data:
        obj.status = data["status"]
    if "tags" in data:
        obj.tags = data["tags"]
    if "video" in data:
        obj.video = data["video"]
    if "links" in data:
        obj.links = data["links"]
    if "docs" in data:
        obj.docs = data["docs"]
    if "notes" in data:
        obj.notas = data["notes"]
    db.commit()
    db.refresh(obj)
    return item_dict(obj)


@app.delete("/api/itens/{item_id}", status_code=204)
def remover_item(item_id: int, db: Session = Depends(get_db)):
    obj = get_item_or_404(db, item_id)
    db.delete(obj)
    db.commit()


# ===================== FRONT-END =====================
# Serve o site (o design Akademía). Mantido por último para não capturar /api/*.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
