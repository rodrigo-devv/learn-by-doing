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


class UTF8JSONResponse(JSONResponse):
    """JSON sempre com 'charset=utf-8' explícito no Content-Type.

    O corpo já é UTF-8 (Starlette usa ensure_ascii=False), mas declarar o
    charset evita qualquer cliente HTTP interpretar acentos como Latin-1.
    """

    media_type = "application/json; charset=utf-8"


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Akademía API",
    version="1.1.0",
    default_response_class=UTF8JSONResponse,
)

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


def projeto_dict(p: models.Projeto) -> dict:
    return {
        "id": str(p.id),
        "title": p.titulo,
        "description": p.descricao or "",
        "tags": p.tags or [],
        "links": p.links or [],
    }


def atividade_dict(a: models.Atividade) -> dict:
    return {
        "id": str(a.id),
        "title": a.titulo,
        "prompt": a.enunciado or "",
        "answers": a.respostas or "",
        "feedback": a.feedback or "",
        "grade": a.nota or "",
        "status": a.status,
        "topics": a.assuntos or [],
        "item_id": str(a.item_id) if a.item_id is not None else None,
    }


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


def get_atividade_or_404(db: Session, atividade_id: int) -> models.Atividade:
    obj = db.get(models.Atividade, atividade_id)
    if not obj:
        raise HTTPException(404, "Atividade não encontrada")
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
            "projetos": db.query(models.Projeto).count(),
            "atividades": db.query(models.Atividade).count(),
        }
        info["db"]["connected"] = True
    except Exception as exc:  # banco inacessível: app de pé, mas degradado
        info["status"] = "degraded"
        info["db"]["error"] = type(exc).__name__
    return info


# ===================== ESTADO COMPLETO =====================
@app.get("/api/state")
def get_state(db: Session = Depends(get_db)):
    """Devolve {weeks, projects, activities} — carregamento inicial do site."""
    semanas = db.scalars(
        select(models.Semana).order_by(models.Semana.ordem, models.Semana.id)
    ).all()
    projetos = db.scalars(
        select(models.Projeto).order_by(models.Projeto.ordem, models.Projeto.id)
    ).all()
    atividades = db.scalars(
        select(models.Atividade).order_by(models.Atividade.ordem, models.Atividade.id)
    ).all()
    return {
        "weeks": [semana_dict(s) for s in semanas],
        "projects": [projeto_dict(p) for p in projetos],
        "activities": [atividade_dict(a) for a in atividades],
    }


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


# ===================== PROJETOS =====================
@app.get("/api/projetos")
def listar_projetos(db: Session = Depends(get_db)):
    projetos = db.scalars(
        select(models.Projeto).order_by(models.Projeto.ordem, models.Projeto.id)
    ).all()
    return [projeto_dict(p) for p in projetos]


@app.post("/api/projetos", status_code=201)
def criar_projeto(payload: schemas.ProjetoCreate, db: Session = Depends(get_db)):
    ordem = db.query(models.Projeto).count()
    obj = models.Projeto(
        titulo=payload.title,
        descricao=payload.description,
        tags=payload.tags,
        links=[l.model_dump() for l in payload.links],
        ordem=ordem,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return projeto_dict(obj)


@app.patch("/api/projetos/{projeto_id}")
def atualizar_projeto(projeto_id: int, payload: schemas.ProjetoUpdate, db: Session = Depends(get_db)):
    obj = db.get(models.Projeto, projeto_id)
    if not obj:
        raise HTTPException(404, "Projeto não encontrado")
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        obj.titulo = data["title"]
    if "description" in data:
        obj.descricao = data["description"]
    if "tags" in data:
        obj.tags = data["tags"]
    if "links" in data:
        obj.links = [l.model_dump() for l in payload.links]
    db.commit()
    db.refresh(obj)
    return projeto_dict(obj)


@app.delete("/api/projetos/{projeto_id}", status_code=204)
def remover_projeto(projeto_id: int, db: Session = Depends(get_db)):
    obj = db.get(models.Projeto, projeto_id)
    if not obj:
        raise HTTPException(404, "Projeto não encontrado")
    db.delete(obj)
    db.commit()


# ===================== ATIVIDADES =====================
def _parse_item_id(raw) -> int | None:
    """Converte item_id vindo como string ('12') ou None para int|None."""
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@app.get("/api/atividades")
def listar_atividades(db: Session = Depends(get_db)):
    atividades = db.scalars(
        select(models.Atividade).order_by(models.Atividade.ordem, models.Atividade.id)
    ).all()
    return [atividade_dict(a) for a in atividades]


@app.post("/api/atividades", status_code=201)
def criar_atividade(payload: schemas.AtividadeCreate, db: Session = Depends(get_db)):
    item_id = _parse_item_id(payload.item_id)
    if item_id is not None:
        get_item_or_404(db, item_id)  # valida o vínculo, se houver
    ordem = db.query(models.Atividade).count()
    obj = models.Atividade(
        titulo=payload.title,
        enunciado=payload.prompt,
        respostas=payload.answers,
        feedback=payload.feedback,
        nota=payload.grade,
        status=payload.status,
        assuntos=payload.topics,
        item_id=item_id,
        ordem=ordem,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return atividade_dict(obj)


@app.patch("/api/atividades/{atividade_id}")
def atualizar_atividade(
    atividade_id: int, payload: schemas.AtividadeUpdate, db: Session = Depends(get_db)
):
    obj = get_atividade_or_404(db, atividade_id)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        obj.titulo = data["title"]
    if "prompt" in data:
        obj.enunciado = data["prompt"]
    if "answers" in data:
        obj.respostas = data["answers"]
    if "feedback" in data:
        obj.feedback = data["feedback"]
    if "grade" in data:
        obj.nota = data["grade"]
    if "status" in data:
        obj.status = data["status"]
    if "topics" in data:
        obj.assuntos = data["topics"]
    if "item_id" in data:
        item_id = _parse_item_id(data["item_id"])
        if item_id is not None:
            get_item_or_404(db, item_id)
        obj.item_id = item_id
    db.commit()
    db.refresh(obj)
    return atividade_dict(obj)


@app.delete("/api/atividades/{atividade_id}", status_code=204)
def remover_atividade(atividade_id: int, db: Session = Depends(get_db)):
    obj = get_atividade_or_404(db, atividade_id)
    db.delete(obj)
    db.commit()


# ===================== FRONT-END =====================
# Serve o site (o design Akademía). Mantido por último para não capturar /api/*.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
