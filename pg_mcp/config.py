from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    databases: dict[str, str]
    max_rows: int = 200
    statement_timeout_ms: int = 5000
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    default_database: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.databases:
            raise ValueError(
                "No database configured. Set DATABASE_URL or PG_MCP_DATABASES (see .env.example)."
            )
        object.__setattr__(self, "default_database", next(iter(self.databases)))


def load_settings() -> Settings:
    load_dotenv()
    raw = os.getenv("PG_MCP_DATABASES")
    if raw:
        databases = json.loads(raw)
        if not isinstance(databases, dict):
            raise ValueError("PG_MCP_DATABASES must be a JSON object of name -> URL")
    elif os.getenv("DATABASE_URL"):
        databases = {"default": os.environ["DATABASE_URL"]}
    else:
        databases = {}

    return Settings(
        databases=databases,
        max_rows=int(os.getenv("PG_MCP_MAX_ROWS", "200")),
        statement_timeout_ms=int(os.getenv("PG_MCP_STATEMENT_TIMEOUT_MS", "5000")),
        llm_api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
    )
