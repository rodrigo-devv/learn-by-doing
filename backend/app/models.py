"""Modelos do banco — espelham o modelo de dados do design Akademía.

O app é organizado em SEMANAS, e cada semana contém ITENS de estudo.
Cada item agrupa tudo que você pode estudar: status, tags, um vídeo do
YouTube, vários links, vários documentos e anotações.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.utcnow()


class Semana(Base):
    """Uma semana do cronograma, ex: 'Semana 1 · Fundamentos'."""

    __tablename__ = "semanas"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)

    itens: Mapped[list["Item"]] = relationship(
        back_populates="semana",
        cascade="all, delete-orphan",
        order_by="Item.ordem",
    )


class Item(Base):
    """Um item de estudo dentro de uma semana.

    status: 'todo' (a fazer) | 'doing' (em andamento) | 'done' (concluído).
    tags:   lista de strings, ex: ["algoritmos", "vídeo"].
    video:  URL do YouTube (string única).
    links:  lista de {"label": ..., "url": ...}.
    docs:   lista de {"label": ..., "url": ...}.
    """

    __tablename__ = "itens"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(10), default="todo")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    video: Mapped[str] = mapped_column(String(500), default="")
    links: Mapped[list] = mapped_column(JSON, default=list)
    docs: Mapped[list] = mapped_column(JSON, default=list)
    notas: Mapped[str] = mapped_column(Text, default="")
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)

    semana_id: Mapped[int] = mapped_column(ForeignKey("semanas.id"))
    semana: Mapped["Semana"] = relationship(back_populates="itens")


class Projeto(Base):
    """Um projeto de estudo com links para GitHub, deploys, etc."""

    __tablename__ = "projetos"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300), default="")
    descricao: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    links: Mapped[list] = mapped_column(JSON, default=list)  # [{label, url}]
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Atividade(Base):
    """Uma atividade/exercício gerado pelo agente sobre assuntos já estudados.

    Fluxo: o usuário conclui um item ('done'), pede ao agente uma atividade,
    o agente gera o `enunciado`. O usuário responde (em `respostas`) e o agente
    corrige, preenchendo `nota` e `feedback`. A nota vira um selo no card do item.

    status: 'pendente' (gerada) | 'entregue' (respondida) | 'corrigida' (com nota).
    assuntos: lista de tópicos cobertos, ex: ["print", "variáveis", "operações"].
    item_id: item de estudo de origem (opcional) — liga a nota ao card.
    """

    __tablename__ = "atividades"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(300), default="")
    enunciado: Mapped[str] = mapped_column(Text, default="")
    respostas: Mapped[str] = mapped_column(Text, default="")
    feedback: Mapped[str] = mapped_column(Text, default="")
    nota: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(12), default="pendente")
    assuntos: Mapped[list] = mapped_column(JSON, default=list)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=_now)

    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("itens.id", ondelete="SET NULL"), nullable=True
    )
