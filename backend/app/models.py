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
