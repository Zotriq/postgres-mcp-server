"""MCP server exposing safe, read-only PostgreSQL tools to AI assistants."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .config import Settings, load_settings
from .database import Database
from .nl2sql import ChatClient, OpenAIChatClient, generate_sql

INSTRUCTIONS = (
    "Read-only PostgreSQL access. Start with list_databases and list_tables, use "
    "describe_table before writing SQL, then run_query. Use ask to let the server write "
    "the SQL from a plain-English question. All queries are read-only and row-limited."
)


def build_server(settings: Settings, llm: ChatClient | None = None) -> MCPServer:
    server = MCPServer("postgres-mcp", instructions=INSTRUCTIONS)
    dbs = {
        name: Database(url, max_rows=settings.max_rows, statement_timeout_ms=settings.statement_timeout_ms)
        for name, url in settings.databases.items()
    }

    def pick(database: str | None) -> Database:
        name = database or settings.default_database
        if name not in dbs:
            raise ValueError(f"Unknown database '{name}'. Available: {', '.join(dbs)}")
        return dbs[name]

    def get_llm() -> ChatClient:
        if llm is not None:
            return llm
        if not settings.llm_api_key:
            raise RuntimeError("The ask tool needs LLM_API_KEY (see .env.example).")
        return OpenAIChatClient(settings.llm_api_key, settings.llm_model, settings.llm_base_url)

    @server.tool()
    def list_databases() -> list[str]:
        """List the configured database names."""
        return list(dbs)

    @server.tool()
    def list_tables(database: str | None = None, schema: str | None = None) -> list[dict[str, Any]]:
        """List tables and views with approximate row counts."""
        return pick(database).list_tables(schema)

    @server.tool()
    def describe_table(table: str, database: str | None = None) -> dict[str, Any]:
        """Show columns, types, primary key and foreign keys for a table (e.g. 'public.orders')."""
        return pick(database).describe_table(table)

    @server.tool()
    def run_query(sql: str, database: str | None = None) -> dict[str, Any]:
        """Run a single read-only SELECT. Writes, DDL and unsafe functions are rejected; rows are capped."""
        return pick(database).run_query(sql)

    @server.tool()
    def explain_query(sql: str, database: str | None = None) -> list[str]:
        """Show the PostgreSQL query plan for a SELECT without running it."""
        return pick(database).explain(sql)

    @server.tool()
    def ask(question: str, database: str | None = None, run: bool = True) -> dict[str, Any]:
        """Answer a plain-English question: writes safe SQL from the live schema and (optionally) runs it."""
        db = pick(database)
        sql = generate_sql(question, db.schema_overview(), get_llm(), max_rows=settings.max_rows)
        if not run:
            return {"sql": sql}
        return db.run_query(sql)

    return server


def main() -> None:
    build_server(load_settings()).run()


if __name__ == "__main__":
    main()
