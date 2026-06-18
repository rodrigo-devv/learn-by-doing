"""Servidor MCP do Akademía.

Dá ao seu Claude ferramentas para montar seu diário de estudos conversando.
Modelo: SEMANAS → ITENS. Cada item tem status, tags, um vídeo (YouTube),
links, documentos e anotações.

Fluxo típico:
  Você: "Quero estudar Engenharia de Dados. Monte um plano de 2 semanas."
  Claude: chama `adicionar_item` várias vezes, agrupando por semana.
  Este servidor: encaminha para a API FastAPI, que salva no banco.
  Site Akademía: mostra tudo no Painel, Cronograma e Detalhe.

As ferramentas só chamam a API REST (única fonte da verdade), então site e
chatbot ficam sempre em sincronia.
"""
import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

# Windows usa cp1252 por padrão; forçar UTF-8 evita mojibake em títulos PT.
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_BASE = os.environ.get("AKADEMIA_API_BASE", "http://127.0.0.1:8000")
# Mesmo token configurado no backend (AKADEMIA_TOKEN). Vazio = sem auth (local).
API_TOKEN = os.environ.get("AKADEMIA_TOKEN", "")

mcp = FastMCP("Akademia")


def _request(method: str, path: str, json: dict | None = None) -> dict | None:
    """Faz uma chamada à API, falha em erro HTTP (ex: 401) e devolve o JSON.

    Sem `raise_for_status`, um 401 voltaria como dado em vez de erro — então
    a verificação é essencial para o token ser realmente respeitado.
    """
    headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
    with httpx.Client(base_url=API_BASE, timeout=15, headers=headers) as cli:
        resp = cli.request(method, path, json=json)
        if resp.status_code == 401:
            raise PermissionError("API exigiu autenticação: confira AKADEMIA_TOKEN.")
        resp.raise_for_status()
        return resp.json() if resp.content else None


def _achar_ou_criar_semana(titulo: str | None) -> str:
    """Devolve o id de uma semana pelo título (cria se não existir).

    Se `titulo` for None/vazio, usa a primeira semana existente ou cria uma.
    """
    semanas = _request("GET", "/api/state").get("weeks", [])

    if titulo:
        alvo = titulo.strip().lower()
        for s in semanas:
            if s["title"].strip().lower() == alvo:
                return s["id"]
        return _request("POST", "/api/semanas", {"title": titulo})["id"]

    if semanas:
        return semanas[0]["id"]
    return _request("POST", "/api/semanas", {"title": "Semana 1"})["id"]


# ===================== CRIAÇÃO =====================
@mcp.tool()
def criar_semana(titulo: str) -> dict:
    """Cria uma semana no cronograma, ex: 'Semana 1 · Fundamentos'.

    Devolve a semana criada com seu `id`.
    """
    return _request("POST", "/api/semanas", {"title": titulo})


@mcp.tool()
def adicionar_item(
    titulo: str,
    semana: str | None = None,
    status: str = "todo",
    tags: list[str] | None = None,
    video: str | None = None,
    links: list[dict] | None = None,
    docs: list[dict] | None = None,
    notas: str | None = None,
) -> dict:
    """Adiciona um item de estudo a uma semana — a ferramenta principal.

    Um item agrupa tudo: um vídeo, vários cursos/links, documentos, tags e
    anotações. Use-a para transformar suas recomendações em itens acionáveis.

    Parâmetros:
      titulo:  o que estudar, ex: "Curso: introdução a algoritmos".
      semana:  título da semana onde colocar. Se não existir, é criada.
               Se omitido, usa a primeira semana (ou cria 'Semana 1').
      status:  'todo' (a fazer), 'doing' (em andamento) ou 'done' (concluído).
      tags:    lista de rótulos, ex: ["algoritmos", "vídeo"].
      video:   URL do YouTube (será embutido no item).
      links:   lista de objetos {"label": "...", "url": "..."} — cursos, artigos.
      docs:    lista de objetos {"label": "...", "url": "..."} — PDFs, documentos.
      notas:   texto livre com resumo, objetivos ou dicas.
    """
    semana_id = _achar_ou_criar_semana(semana)
    payload = {
        "title": titulo,
        "status": status,
        "tags": tags or [],
        "video": video or "",
        "links": links or [],
        "docs": docs or [],
        "notes": notas or "",
    }
    return _request("POST", f"/api/semanas/{semana_id}/itens", payload)


# ===================== PROJETOS =====================
@mcp.tool()
def adicionar_projeto(
    titulo: str,
    descricao: str = "",
    tags: list[str] | None = None,
    links: list[dict] | None = None,
) -> dict:
    """Registra um projeto de estudo com links para GitHub, deploy, etc.

    Parâmetros:
      titulo:   nome do repositório ou projeto, ex: "learning-by-doing".
      descricao: resumo curto do que o projeto faz.
      tags:     rótulos, ex: ["fastapi", "react", "mcp"].
      links:    lista de {"label": "...", "url": "..."}.
                Cole URLs do GitHub, Railway, Vercel, AWS — o site detecta o ícone.
    """
    payload = {
        "title": titulo,
        "description": descricao,
        "tags": tags or [],
        "links": links or [],
    }
    return _request("POST", "/api/projetos", payload)


# ===================== ATUALIZAÇÃO =====================
@mcp.tool()
def atualizar_status_item(item_id: str, status: str) -> dict:
    """Muda o status de um item: 'todo', 'doing' ou 'done'.

    Use `listar_estado` para descobrir o `item_id`.
    """
    return _request("PATCH", f"/api/itens/{item_id}", {"status": status})


# ===================== LEITURA =====================
@mcp.tool()
def listar_estado() -> dict:
    """Devolve todas as semanas e seus itens (com ids, status, vídeo, links, docs).

    Use antes de atualizar algo, para saber os ids e o que já existe.
    """
    return _request("GET", "/api/state")


@mcp.tool()
def resumo_estudos() -> dict:
    """Panorama: semanas, itens por status e total de projetos cadastrados."""
    estado = _request("GET", "/api/state")
    itens = [it for w in estado.get("weeks", []) for it in w["items"]]
    return {
        "semanas": len(estado.get("weeks", [])),
        "itens": len(itens),
        "a_fazer": sum(1 for it in itens if it["status"] == "todo"),
        "em_andamento": sum(1 for it in itens if it["status"] == "doing"),
        "concluidos": sum(1 for it in itens if it["status"] == "done"),
        "projetos": len(estado.get("projects", [])),
    }


if __name__ == "__main__":
    # AKADEMIA_MCP_TRANSPORT=stdio (padrão, p/ Claude Desktop local) ou
    # "streamable-http" (p/ hospedar na nuvem e conectar como connector remoto).
    transport = os.environ.get("AKADEMIA_MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run()
    else:
        # host/porta vêm de env (no Railway, use --host 0.0.0.0 e a porta $PORT).
        mcp.settings.host = os.environ.get("HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8001"))
        mcp.run(transport=transport)
