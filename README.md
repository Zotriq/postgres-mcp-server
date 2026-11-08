# Postgres MCP Server

![tests](https://github.com/Zotriq/postgres-mcp-server/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-server-000000?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

An [MCP](https://modelcontextprotocol.io/) server that lets AI assistants like Claude Desktop, Cursor or
Claude Code **explore and query a PostgreSQL database in plain English, safely**.

Ask *"Which customers spent the most last quarter?"* and the assistant inspects the live schema, writes the SQL,
runs it read-only and answers from the results.

## Why it's safe to point at a real database

Letting an AI run SQL is only useful if it can't break anything. Every query passes through **three layers**:

| Layer | What it does |
|---|---|
| **SQL guard** (`sql_guard.py`) | Parses the query with `sqlglot` and only allows a single `SELECT`. Rejects `INSERT/UPDATE/DELETE`, DDL, `COPY`, `SELECT INTO`, row locks, data-modifying CTEs, and risky functions like `pg_sleep`, `pg_read_file` and `dblink`. |
| **Row cap** | Adds or tightens a `LIMIT` on every query (default 200 rows), so one question can't dump a whole table. |
| **Database session** | Every query runs in a `READ ONLY` transaction with a `statement_timeout` (default 5 s), so even a query that slipped past the guard can't write or run forever. |

For production, connect with a database user that only has `SELECT` grants as well.

## Tools

| Tool | Description |
|---|---|
| `list_databases` | Configured databases (you can connect several at once) |
| `list_tables` | Tables and views with approximate row counts |
| `describe_table` | Columns, types, primary key and foreign keys |
| `run_query` | Run a read-only `SELECT` with safety checks and a row cap |
| `explain_query` | Show the query plan without running the query |
| `ask` | Plain-English question → SQL written from the live schema → results. Rejected SQL is sent back to the model once to fix. |

## How `ask` works

```
question ──► schema overview (tables, columns, PKs, FKs) ──► LLM writes SQL
                                                               │
                         rejected? ◄── SQL guard ◄─────────────┘
                         └─► one repair attempt with the error message
                                                               │
                                            read-only execution ──► rows (JSON)
```

`ask` works with any OpenAI-compatible API: OpenAI, Groq, OpenRouter, or a local model through Ollama.

## Quick start

```bash
git clone https://github.com/Zotriq/postgres-mcp-server.git
cd postgres-mcp-server
pip install -e .
cp .env.example .env      # set DATABASE_URL (and LLM_API_KEY for the ask tool)
```

Want sample data? Load the demo shop database:

```bash
psql "$DATABASE_URL" -f examples/shop_schema.sql
```

### Use it in Claude Desktop

Add this to `claude_desktop_config.json` (see [`examples/claude_desktop_config.json`](examples/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "pg-mcp",
      "env": { "DATABASE_URL": "postgresql://readonly_user:password@localhost:5432/shop" }
    }
  }
}
```

### Several databases

```env
PG_MCP_DATABASES={"shop": "postgresql://...", "analytics": "postgresql://..."}
```

Every tool takes an optional `database` argument; the first one is the default.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | – | Single database connection |
| `PG_MCP_DATABASES` | – | JSON map of name → URL (overrides `DATABASE_URL`) |
| `PG_MCP_MAX_ROWS` | `200` | Maximum rows returned per query |
| `PG_MCP_STATEMENT_TIMEOUT_MS` | `5000` | Per-query timeout |
| `LLM_API_KEY` | – | Key for the `ask` tool |
| `LLM_BASE_URL` | OpenAI | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | `gpt-4o-mini` | Model used to write SQL |

## Tests

34 tests cover the SQL guard (17 attack patterns), the read-only session, timeouts, schema discovery and the
full MCP tool flow against a real PostgreSQL database. The LLM is mocked.

```bash
pip install -e ".[dev]"
PG_TEST_URL=postgresql://postgres@localhost:5432/postgres pytest
```

GitHub Actions runs the suite against PostgreSQL 16 on every push.

## Project structure

```
pg_mcp/
  server.py      MCP server and tool definitions
  database.py    read-only sessions, schema discovery, query execution
  sql_guard.py   SQL parsing and safety rules
  nl2sql.py      plain-English → SQL with validation and one repair attempt
  config.py      settings from environment variables
examples/        demo schema and Claude Desktop config
tests/           pytest suite
```

## License

MIT © Zohaib Tariq
