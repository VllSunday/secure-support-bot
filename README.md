# Secure Support Bot

A small Telegram support assistant built as a practical lab for defensive LLM application design.
It keeps company data isolated, treats retrieved documents as untrusted input, and requires
server-side authorization and explicit confirmation before any state-changing action.

The current slice uses a deterministic mock responder, persistent SQLite storage, a Telegram polling
entrypoint, strict tool schemas, input/output guards, and security-focused tests. An optional LLM
provider is available behind the same interfaces without giving the model ownership of permissions
or refund execution.

## Security invariants

- Telegram identity and permissions come only from trusted server state.
- Retrieval is scoped to the user's company before document ranking.
- Model output is never executed as code or SQL.
- Only `get_order` and `refund` exist in the tool registry.
- Refunds require an exact, expiring confirmation bound to user, order, amount, and request ID.
- A timeout or disagreement in a mandatory risk check produces `review`, never execution.
- Reusing a request ID cannot create a second refund.
- Every decision is recorded with machine-readable reason codes.

## Local setup

Create a virtual environment, install the project, and run the tests:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Copy `.env.example` to `.env` and set two non-default signing secrets. The mock application can
use SQLite and does not need an LLM API key. To start the Telegram bot, add a BotFather token and
run:

```powershell
.\.venv\Scripts\python.exe -m secure_support_bot.main
```

The bot uses private chats for order and refund flows. The Telegram token stays in the environment
and is never passed to a model or written to the audit log.

## Optional LLM mode

The answer layer can be switched to OpenAI without changing authorization or action code:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,llm]"
```

Set `BOT_MODE=llm`, `OPENAI_API_KEY`, and `OPENAI_MODEL` in `.env`. The OpenAI adapter receives
only the user question and quarantined document facts as data. It has no tools, order repository,
Telegram token, or permission context. If the provider fails or returns an empty response, the bot
returns `review` and does not expose a partial model answer.

The `/start` response always displays the active mode.

## Development checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src tests
```

The test suite verifies tenant isolation, prompt-injection handling, strict tool arguments, failed
risk checks, exact confirmation, persistent state, and idempotent refunds.

## Explain the security model

Use [`docs/security-map.md`](docs/security-map.md) as the short architecture walkthrough. It includes
the request flow, responsibility table, refund explanation, and common defense questions. An editable
Excalidraw version is available at [`docs/security-map.excalidraw`](docs/security-map.excalidraw).

## Container run

For a local PostgreSQL-backed run, set `TELEGRAM_BOT_TOKEN`, `COMPANY_ASSIGNMENT_SECRET`,
`CONFIRMATION_HMAC_SECRET`, and optionally `POSTGRES_PASSWORD` in the shell, then run:

```powershell
docker compose up --build
```

The production configuration refuses the development signing-secret defaults. The database volume
contains only fictional training data and can be removed when the local exercise is complete.

