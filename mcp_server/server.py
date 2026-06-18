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
import json
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
def atualizar_status_item(item_id: str | int, status: str) -> dict:
    """Muda o status de um item: 'todo', 'doing' ou 'done'.

    Use `listar_estado` para descobrir o `item_id`. Aceita id como "12" ou 12.
    """
    return _request("PATCH", f"/api/itens/{str(item_id)}", {"status": status})


# ===================== ATIVIDADES =====================
def _achar_item_id(titulo: str | None) -> str | None:
    """Acha o id de um item pelo título (case-insensitive). None se não achar."""
    if not titulo:
        return None
    alvo = titulo.strip().lower()
    estado = _request("GET", "/api/state")
    for w in estado.get("weeks", []):
        for it in w.get("items", []):
            if it.get("title", "").strip().lower() == alvo:
                return it["id"]
    return None


@mcp.tool()
def gerar_atividade(
    titulo: str,
    questoes: list[dict],
    item: str | None = None,
    assuntos: list[str] | None = None,
) -> dict:
    """Cria uma atividade com múltiplas questões de tipos variados.

    Use depois que o usuário concluir um item e pedir uma atividade. Cada questão
    aparece num card interativo no site — o usuário navega questão por questão e
    responde com o input adequado ao tipo. Depois peça para corrigir com
    `corrigir_atividade`.

    Parâmetros:
      titulo:   nome curto, ex: "Atividade: Fundamentos de Python".
      questoes: lista de questões. Cada uma é um dict com:
        tipo        (obrigatório) — "codigo" | "multipla_escolha" | "escolha_cards" | "dissertativa"
        texto       (obrigatório) — o enunciado da questão
        hint        (opcional)   — dica ou instrução adicional mostrada abaixo da pergunta
        linguagem   (opcional)   — "python" | "javascript" | "typescript" | "java" | "cpp"
                                   (use em questões de código — mostra emoji e extensão)
        dificuldade (opcional)   — "Fácil" | "Média" | "Difícil"
        opcoes      (obrigatório para multipla_escolha e escolha_cards) — lista de:
                    {"label": "A", "texto": "...", "codigo": "..."}
                    use "texto" para texto simples, "codigo" para blocos de código

    Exemplos de questões:

      Código Python:
        {"tipo": "codigo", "linguagem": "python", "dificuldade": "Fácil",
         "texto": "Como você imprime 'Olá, mundo!'?",
         "hint": "Use a função print() com a string entre aspas."}

      Múltipla escolha:
        {"tipo": "multipla_escolha", "dificuldade": "Média",
         "texto": "Qual é a f-string correta em Python?",
         "opcoes": [
           {"label": "A", "texto": "print(f'Olá, {nome}')"},
           {"label": "B", "texto": "f'Olá, {nome}'"},
           {"label": "C", "texto": "'Olá, ' + {nome}"}
         ]}

      Escolha entre blocos de código (cards visuais):
        {"tipo": "escolha_cards", "linguagem": "python",
         "texto": "Qual trecho lê o nome e exibe a saudação correta?",
         "opcoes": [
           {"label": "A", "codigo": "nome = input()\\nprint(nome)"},
           {"label": "B", "codigo": "nome = input('Nome: ')\\nprint(f'Olá, {nome}!')"}
         ]}

      Dissertativa (texto livre com Markdown):
        {"tipo": "dissertativa", "dificuldade": "Difícil",
         "texto": "Explique a diferença entre variáveis e constantes em Python.",
         "hint": "Escreva com pelo menos 2 exemplos de código."}

      item:     título do item de estudo de origem (vincula a nota ao card do item).
      assuntos: tópicos cobertos, ex: ["print", "variáveis", "f-strings"].
    """
    payload = {
        "title": titulo,
        "prompt": json.dumps(questoes, ensure_ascii=False),
        "status": "pendente",
        "topics": assuntos or [],
        "item_id": _achar_item_id(item),
    }
    return _request("POST", "/api/atividades", payload)


@mcp.tool()
def corrigir_atividade(atividade_id: str | int, nota: str | int | float, feedback: str) -> dict:
    """Corrige uma atividade respondida: registra a nota e o feedback.

    Marca a atividade como 'corrigida'. A `nota` vira um selo no card do item
    vinculado e aparece na aba Atividades. Use `listar_atividades` para ver as
    respostas do usuário (campo `answers`) antes de corrigir.

    Parâmetros:
      atividade_id: id da atividade (de `listar_atividades`). Aceita "2" ou 2.
      nota:         a nota, ex: "8.5", "9/10" ou "A". Aceita texto ou número.
      feedback:     comentários da correção (o que acertou, o que revisar).
    """
    # O gateway MCP pode entregar ids/notas numéricos como int/float; normaliza
    # para string para casar com a API (que trata id e grade como texto).
    return _request(
        "PATCH",
        f"/api/atividades/{str(atividade_id)}",
        {"grade": str(nota), "feedback": feedback, "status": "corrigida"},
    )


@mcp.tool()
def listar_atividades() -> dict:
    """Lista todas as atividades (enunciado, respostas, status, nota, feedback).

    Use para descobrir ids, ler as respostas do usuário e ver o que falta corrigir.
    """
    return {"activities": _request("GET", "/api/atividades")}


# ===================== LEITURA =====================
@mcp.tool()
def listar_estado() -> dict:
    """Devolve todas as semanas e seus itens (com ids, status, vídeo, links, docs).

    Use antes de atualizar algo, para saber os ids e o que já existe.
    """
    return _request("GET", "/api/state")


@mcp.tool()
def listar_projetos() -> dict:
    """Lista todos os projetos cadastrados (id, título, descrição, tags, links).

    Use para ver projetos existentes antes de adicionar um novo ou para
    mostrar ao usuário o que já foi registrado.
    """
    return {"projects": _request("GET", "/api/projetos")}


@mcp.tool()
def resumo_estudos() -> dict:
    """Panorama geral: semanas, itens por status, projetos e atividades.

    Use como primeiro passo em qualquer sessão de estudo para ter contexto
    antes de sugerir o que fazer a seguir.
    """
    estado = _request("GET", "/api/state")
    itens = [it for w in estado.get("weeks", []) for it in w["items"]]
    atividades = estado.get("activities", [])
    return {
        "semanas": len(estado.get("weeks", [])),
        "itens": len(itens),
        "a_fazer": sum(1 for it in itens if it["status"] == "todo"),
        "em_andamento": sum(1 for it in itens if it["status"] == "doing"),
        "concluidos": sum(1 for it in itens if it["status"] == "done"),
        "projetos": len(estado.get("projects", [])),
        "atividades": len(atividades),
        "atividades_pendentes": sum(1 for a in atividades if a["status"] == "pendente"),
        "atividades_corrigidas": sum(1 for a in atividades if a["status"] == "corrigida"),
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
