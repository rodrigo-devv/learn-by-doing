# Akademía

A study journal you fill by talking to Claude instead of clicking through forms.

The annoyance that started this: planning what to study takes longer than studying. You ask an AI for a curriculum, it writes a good list in the chat, and the list is gone as soon as you close the tab. Here the agent writes into the app instead. Say "I want to move into data engineering, plan out two weeks for me" and Claude calls a few MCP tools; the plan lands as weeks and items you can work through.

## What the app does

Everything lives inside a week, and each week holds items. An item is one thing you decided to study, and it carries everything related to it:

- a status: `todo`, `doing` or `done`
- free tags, so you can group things your own way
- one YouTube video, embedded in the item view
- any number of links (courses, articles)
- any number of documents (PDFs, slides)
- a notes field for goals and reminders

Two other things sit beside the schedule. Projects is a plain list of what you have built or are building, with links to GitHub, Railway, Vercel and so on. Activities are exercises the agent writes for you once you mark an item as done: you answer question by question in the UI, the agent grades it, and the grade shows up as a badge on the item it came from.

The site has four views: Painel (progress overview), Cronograma (the weeks and their items), Atividades and Projetos. The interface is in Portuguese. The code keeps Portuguese names for database columns and API fields, which is also why the MCP tools are named in Portuguese.

## How it fits together

```
You talk to Claude  ──►  Claude calls the MCP tools
                               │
                               ▼
                      MCP server  ──►  FastAPI  ──►  database
                                                       │
        Akademía site (React)  ◄── reads the same data ─┘
```

- `backend/` is the FastAPI app and the database. It owns the data and also serves the site.
- `mcp_server/` is the MCP server. It gives Claude tools like `adicionar_item` and `gerar_atividade`, and forwards every call to the REST API.
- `frontend/` is the site. One HTML file with React 18 and Babel pulled from unpkg and compiled in the browser, so there is no build step and nothing to install.

The MCP server never touches the database directly. It only talks to the API, which is what keeps the site and the chat in sync.

## Running it locally

### 1. Backend and site

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows (PowerShell: .venv\Scripts\Activate.ps1)
source .venv/bin/activate       # macOS and Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Site: <http://127.0.0.1:8000>
- Interactive API docs: <http://127.0.0.1:8000/docs>

`akademia.db` (SQLite) is created on first run in the repository root. There is nothing to configure. If you set `DATABASE_URL`, the app uses that instead, which is how the Postgres deploy works.

Open the site through the API address rather than double-clicking the HTML file. The page fetches `/api/*` from the same origin, and that only works when the API is the one serving it.

### 2. MCP server

```bash
cd mcp_server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Then point Claude Desktop at it. Edit `%APPDATA%\Claude\claude_desktop_config.json` (on macOS, `~/Library/Application Support/Claude/claude_desktop_config.json`) and add:

```json
{
  "mcpServers": {
    "akademia": {
      "command": "C:\\Users\\rodrigo\\development\\projects\\learn-by-doing\\mcp_server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\rodrigo\\development\\projects\\learn-by-doing\\mcp_server\\server.py"],
      "env": { "AKADEMIA_API_BASE": "http://127.0.0.1:8000" }
    }
  }
}
```

Restart Claude Desktop. The backend from step 1 has to be running, since the MCP server calls it for everything.

Claude Code needs one command:

```bash
claude mcp add akademia -- C:\...\mcp_server\.venv\Scripts\python.exe C:\...\mcp_server\server.py
```

## Using it

Talk to Claude the way you would talk to a person:

> I want to work in data engineering. Build me a two-week plan: create the weeks and add items with YouTube videos, course links, documents, and a note about the goal of each one.

Claude calls the tools, the API saves the result, and the site shows it in Painel and Cronograma. Click an item to see the embedded video, its links, documents and notes.

When you finish an item, ask for an activity. The agent writes the questions, you answer them in the UI, and then ask it to grade. The grade appears on the item card.

### MCP tools

| Tool | What it does |
|---|---|
| `criar_semana(titulo)` | Creates a week. |
| `adicionar_item(titulo, semana, status, tags, video, links, docs, notas)` | Adds a study item, creating the week if it doesn't exist yet. This is the one used most. |
| `adicionar_projeto(titulo, descricao, tags, links)` | Registers a project with links. The site picks an icon based on the URL. |
| `atualizar_status_item(item_id, status)` | Moves an item between `todo`, `doing` and `done`. |
| `gerar_atividade(titulo, questoes, item, assuntos)` | Creates an activity with multiple questions. A question can be code, multiple choice, card choice or free text. |
| `corrigir_atividade(atividade_id, nota, feedback)` | Records the grade and the feedback, and marks the activity as graded. |
| `listar_atividades()` | Lists activities with the answers, useful before grading. |
| `listar_estado()` | Returns weeks and items with their ids. |
| `listar_projetos()` | Lists the registered projects. |
| `resumo_estudos()` | Counts weeks, items by status, projects and activities. |

## Data model

```
Week { id, title, items: [
  Item { id, title, status, tags[], video, links:[{label,url}], docs:[{label,url}], notes }
] }

Project { id, title, description, tags[], links:[{label,url}] }

Activity { id, title, prompt, answers, feedback, grade, status, topics[], item_id }
```

An activity's `prompt` holds the questions as JSON. `item_id` points back to the item the activity came from, which is how the grade reaches the item card. Ids are integers in the database and come back as strings, because the frontend treats them as strings.

## HTTP API

| Method and path | Purpose |
|---|---|
| `GET /api/health` | Service status: active database, connection, whether auth is on, version, row counts. Never requires a token. |
| `GET /api/state` | Everything the site loads at startup: `{weeks, projects, activities}`. |
| `POST /api/semanas`, `PATCH/DELETE /api/semanas/{id}` | Create, rename and delete weeks. |
| `POST /api/semanas/{id}/itens` | Add an item to a week. |
| `PATCH/DELETE /api/itens/{id}` | Update or delete an item. |
| `GET/POST /api/projetos`, `PATCH/DELETE /api/projetos/{id}` | Projects. |
| `GET/POST /api/atividades`, `PATCH/DELETE /api/atividades/{id}` | Activities. |

## Authentication

Set `AKADEMIA_TOKEN` and the API requires it on every `/api/*` route except `/api/health`. It accepts `Authorization: Bearer <token>` or `X-API-Key: <token>`.

Leave the variable unset and auth stays off, which is the default for local use.

All three pieces read the same variable:

- the site asks for the token once and keeps it in `localStorage`
- the MCP server sends it on every request
- anything else, such as curl or a script, sends it as a header

## Deploying

The repository is set up for Railway. Postgres comes from `DATABASE_URL`, auth from `AKADEMIA_TOKEN`, and the deploy files (`Procfile`, `requirements.txt`, `.python-version`) sit at the root.

1. Push the whole repository to GitHub.
2. On Railway: New Project, then Deploy from GitHub repo.
3. Add a database, PostgreSQL. Railway creates `DATABASE_URL` and injects it into the service.
4. On the web service, under Variables, add `AKADEMIA_TOKEN` with a strong secret.
5. Under Settings, Deploy, check the start command in case Railpack doesn't read the `Procfile`:
   ```
   uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
   ```
6. Deploy. You get a public URL.
7. Open it, paste the token on the access screen, and it works from any device.

To connect Claude to the deployed backend you have two options.

Point your local MCP server at the cloud:

```json
"env": {
  "AKADEMIA_API_BASE": "https://your-app.up.railway.app",
  "AKADEMIA_TOKEN": "your-secret"
}
```

Or host `mcp_server/` as a second Railway service with

```
AKADEMIA_MCP_TRANSPORT=streamable-http
AKADEMIA_API_BASE=https://your-app.up.railway.app
AKADEMIA_TOKEN=your-secret
```

and the start command `python mcp_server/server.py`. Then add that service's URL as a connector in Claude, and no device needs anything installed.

A small web service plus a small Postgres on Railway's Hobby plan runs around US$5/month.

## License

MIT. See [LICENSE](LICENSE).
