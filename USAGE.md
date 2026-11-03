# worklog-mcp usage

English documentation comes first, matching README style. A Portuguese section is included below.

- [English](#english)
- [Portugues](#portugues)

---

## English

Quick reference for the MCP server that logs and checks worklogs across multiple providers (Jira Cloud, Redmine, GitHub, Artia, SNTL) from any MCP client.

### 1. Prerequisites

- `uv` installed (Python/dependencies/runtime):
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Account in one supported provider with permission to log work:
  - Jira Cloud
  - Redmine
  - GitHub
  - Artia
  - SNTL

### 2. Environment Variables by Provider

#### 2.1 Jira Cloud

| Variable | Required | Description |
|---|---|---|
| `JIRA_BASE_URL` | yes | `https://<your-instance>.atlassian.net` (HTTPS and `*.atlassian.net`) |
| `JIRA_EMAIL` | yes | Atlassian account email |
| `JIRA_API_TOKEN` | yes | Classic API token |
| `JIRA_DAILY_JQL` | no | JQL template for `issue_key="daily"`. `{month}` and `{year}` are filled from worklog date. |

Use a classic Jira API token (not "with scopes") for best compatibility with team-managed projects.

#### 2.2 Redmine

| Variable | Required | Description |
|---|---|---|
| `REDMINE_URL` | yes | Redmine base URL, for example `https://redmine.example.com` |
| `REDMINE_API_KEY` | yes | Redmine API key from account settings |

#### 2.3 GitHub

| Variable | Required | Description |
|---|---|---|
| `GITHUB_TOKEN` | yes | Personal Access Token with `repo` and `user` scopes |
| `GITHUB_REPO` | no | Default repo (`owner/repo`) for shorthand issue references |

#### 2.4 Artia

| Variable | Required | Description |
|---|---|---|
| `ARTIA_CLIENT_ID` | yes | Client ID from Artia integrations |
| `ARTIA_SECRET` | yes | Integration secret |
| `ARTIA_ACCOUNT_ID` | yes | Account/workspace id |
| `ARTIA_FOLDER_ID` | no | Default folder for `search_tasks` |

#### 2.5 SNTL

| Variable | Required | Description |
|---|---|---|
| `SNTL_USERNAME` | yes | SNTL login username |
| `SNTL_PASSWORD` | yes | SNTL login password |
| `SNTL_API_URL` | no | SNTL API URL. Default: `https://back-end.viptech.com.br` |

Task ids are the numeric `#id` shown in SNTL. `search_tasks` lists your own tasks; `native_query` takes state groups `ni`, `ep`, `c`, or `all` (default `ni,ep`). Entries must end by midnight, and the result carries the approval `status` (`pending` or `auto`).

#### 2.6 Provider Selection

| Variable | Required | Description |
|---|---|---|
| `WORK_PROVIDER` | no | Active provider: `jira`, `redmine`, `github`, `artia`, `sntl`. Default: `jira`. |

Variables can come from `.env` next to root `server.py` or from the MCP client environment.

### 3. Register This Server in an MCP Client

Keep paths generic and machine-local. Suggested shell variables:

```powershell
$env:UV_PATH = "C:/path/to/uv.exe"
$env:MCP_PROJECT_DIR = "C:/path/to/mcp-worklog-reg"
```

Provider-ready environment blocks (PowerShell):

- They set environment variables in the current terminal session only.
- They are useful for quick tests and temporary provider switching.
- They are not the same as editing `.env`, which persists values in a file for reuse.
- If both are present, MCP client-provided env values usually take precedence.

```powershell
# Jira
$env:WORK_PROVIDER = "jira"
$env:JIRA_BASE_URL = "https://your-company.atlassian.net"
$env:JIRA_EMAIL = "you@example.com"
$env:JIRA_API_TOKEN = "your-token"

# Redmine
$env:WORK_PROVIDER = "redmine"
$env:REDMINE_URL = "https://redmine.example.com"
$env:REDMINE_API_KEY = "your-key"

# GitHub
$env:WORK_PROVIDER = "github"
$env:GITHUB_TOKEN = "your-token"
$env:GITHUB_REPO = "owner/repo"

# Artia
$env:WORK_PROVIDER = "artia"
$env:ARTIA_CLIENT_ID = "your-client-id"
$env:ARTIA_SECRET = "your-secret"
$env:ARTIA_ACCOUNT_ID = "your-account-id"
$env:ARTIA_FOLDER_ID = "optional-folder-id"

# SNTL
$env:WORK_PROVIDER = "sntl"
$env:SNTL_USERNAME = "your-username"
$env:SNTL_PASSWORD = "your-password"
```

#### 3.1 stdio server entry

Any MCP client that supports stdio can start this server with `uv --directory <repo> run server.py`. Add an entry like this to the `mcpServers` section of its configuration:

```json
{
  "mcpServers": {
    "worklog-mcp": {
      "command": "C:/path/to/uv.exe",
      "args": ["--directory", "C:/path/to/mcp-worklog-reg", "run", "server.py"],
      "env": {
        "WORK_PROVIDER": "jira",
        "JIRA_BASE_URL": "https://your-company.atlassian.net",
        "JIRA_EMAIL": "you@example.com",
        "JIRA_API_TOKEN": "your-token"
      }
    }
  }
}
```

If your client uses TOML instead of JSON, map the same fields (`command`, `args`, `env`) in its MCP section.

#### 3.2 Provider-ready `env` snippets

```json
{
  "WORK_PROVIDER": "jira",
  "JIRA_BASE_URL": "https://your-company.atlassian.net",
  "JIRA_EMAIL": "you@example.com",
  "JIRA_API_TOKEN": "your-token"
}
```

```json
{
  "WORK_PROVIDER": "redmine",
  "REDMINE_URL": "https://redmine.example.com",
  "REDMINE_API_KEY": "your-key"
}
```

```json
{
  "WORK_PROVIDER": "github",
  "GITHUB_TOKEN": "your-token",
  "GITHUB_REPO": "owner/repo"
}
```

```json
{
  "WORK_PROVIDER": "artia",
  "ARTIA_CLIENT_ID": "your-client-id",
  "ARTIA_SECRET": "your-secret",
  "ARTIA_ACCOUNT_ID": "your-account-id",
  "ARTIA_FOLDER_ID": "optional-folder-id"
}
```

```json
{
  "WORK_PROVIDER": "sntl",
  "SNTL_USERNAME": "your-username",
  "SNTL_PASSWORD": "your-password"
}
```

### 4. Tools (7)

This server is read/append only (least privilege). It does not create/edit/transition/assign/delete issues.

| Tool | Purpose | Main args |
|---|---|---|
| `whoami` | Validate auth and return identity | none |
| `search_tasks` | Find tasks | `query`, `native_query`, `max_results` |
| `get_task` | Compact task view | `task_id` |
| `add_comment` | Add comment | `task_id`, `comment` |
| `log_work` | Log one work entry | `task_id`, `time_spent`, `started?`, `comment?` |
| `log_work_batch` | Log multiple entries | `entries`, `skip_duplicates?` |
| `get_worklogs` | List worklogs | `task_id`, `mine_only?` |

Formats:
- `time_spent`: `2:40` or `1h 30m` / `45m` / `2h`
- `started`: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`

### 5. Natural Language Examples

- "log 1h30m on PROJ-123 with comment 'fix X' today"
- "show my worklogs from PROJ-123"
- "add comment 'fix deployed' to PROJ-123"

For spreadsheet-like batch input:
1. Use the provided date.
2. Parse each row into task + duration + comment.
3. Show a preview before execution.
4. Call `log_work_batch` and report skipped duplicates.

### 6. Fast Auth Check

```powershell
uv run python -c "from src.services.provider_registry import registry; print(registry.get().whoami())"
```

---

## Português

Guia rápido do servidor MCP para lançar e conferir horas em Jira Cloud, Redmine, GitHub, Artia e SNTL a partir de qualquer cliente MCP.

### 1. Pré-requisitos

- `uv` instalado:
  `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- Conta no provedor com permissão para apontar horas.

### 2. Variáveis de ambiente

- Jira: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_DAILY_JQL` (opcional)
- Redmine: `REDMINE_URL`, `REDMINE_API_KEY`
- GitHub: `GITHUB_TOKEN`, `GITHUB_REPO` (opcional)
- Artia: `ARTIA_CLIENT_ID`, `ARTIA_SECRET`, `ARTIA_ACCOUNT_ID`, `ARTIA_FOLDER_ID` (opcional)
- SNTL: `SNTL_USERNAME`, `SNTL_PASSWORD`, `SNTL_API_URL` (opcional)
- Seletor: `WORK_PROVIDER` (`jira`, `redmine`, `github`, `artia`, `sntl`)

Pode vir do `.env` ou do ambiente do cliente MCP.

No SNTL, o id da tarefa é o `#id` numérico; `search_tasks` lista as suas tarefas e `native_query` aceita `ni`, `ep`, `c` ou `all` (padrão `ni,ep`). O lançamento precisa terminar até meia-noite, e o retorno traz o `status` de aprovação (`pending` ou `auto`).

### 3. Registrar em um cliente MCP

Em qualquer cliente: iniciar este servidor por stdio com `uv --directory <repo> run server.py` e injetar as variáveis em `env`, na seção `mcpServers` (JSON) ou no equivalente em TOML, com os campos `command`, `args` e `env`.

Blocos de `env` por provedor (copiar/colar):

- Esses blocos definem variáveis no processo/sessão atual do cliente.
- São úteis para teste rápido e troca temporária de provedor.
- Não é a mesma coisa que editar `.env`, que persiste valores em arquivo para reuso.
- Se ambos existirem, variáveis enviadas pelo cliente MCP normalmente têm precedência.

```json
{
  "WORK_PROVIDER": "jira",
  "JIRA_BASE_URL": "https://your-company.atlassian.net",
  "JIRA_EMAIL": "you@example.com",
  "JIRA_API_TOKEN": "your-token"
}
```

```json
{
  "WORK_PROVIDER": "redmine",
  "REDMINE_URL": "https://redmine.example.com",
  "REDMINE_API_KEY": "your-key"
}
```

```json
{
  "WORK_PROVIDER": "github",
  "GITHUB_TOKEN": "your-token",
  "GITHUB_REPO": "owner/repo"
}
```

```json
{
  "WORK_PROVIDER": "artia",
  "ARTIA_CLIENT_ID": "your-client-id",
  "ARTIA_SECRET": "your-secret",
  "ARTIA_ACCOUNT_ID": "your-account-id",
  "ARTIA_FOLDER_ID": "optional-folder-id"
}
```

```json
{
  "WORK_PROVIDER": "sntl",
  "SNTL_USERNAME": "seu-usuario",
  "SNTL_PASSWORD": "sua-senha"
}
```

### 4. Tools

`whoami`, `search_tasks`, `get_task`, `add_comment`, `log_work`, `log_work_batch`, `get_worklogs`.

### 5. Teste rápido

```powershell
uv run python -c "from src.services.provider_registry import registry; print(registry.get().whoami())"
```
