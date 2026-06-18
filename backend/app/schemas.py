"""Schemas Pydantic.

Os nomes dos campos seguem os do front-end (title, status, tags, video,
links, docs, notes / weeks, items) para que o site e o JSON da API conversem
sem tradução. As colunas do banco estão em PT; a conversão acontece em main.py.
"""
from pydantic import BaseModel, Field


class LinkDoc(BaseModel):
    label: str = ""
    url: str = ""


class SemanaCreate(BaseModel):
    title: str = "Nova semana"


class SemanaUpdate(BaseModel):
    title: str


class ItemCreate(BaseModel):
    title: str = "Novo item"
    status: str = "todo"  # todo | doing | done
    tags: list[str] = Field(default_factory=list)
    video: str = ""
    links: list[LinkDoc] = Field(default_factory=list)
    docs: list[LinkDoc] = Field(default_factory=list)
    notes: str = ""


class ItemUpdate(BaseModel):
    """Atualização parcial: só os campos enviados são alterados."""

    title: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    video: str | None = None
    links: list[LinkDoc] | None = None
    docs: list[LinkDoc] | None = None
    notes: str | None = None


class ProjetoCreate(BaseModel):
    title: str = "Novo projeto"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    links: list[LinkDoc] = Field(default_factory=list)


class ProjetoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    links: list[LinkDoc] | None = None
