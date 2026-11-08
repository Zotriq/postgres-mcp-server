"""Turn a plain-English question into a safe SQL query using any OpenAI-compatible LLM."""

from __future__ import annotations

import re
from typing import Protocol

from .sql_guard import UnsafeQueryError, check_query

SYSTEM_PROMPT = """You write PostgreSQL queries for a read-only analytics assistant.

Rules:
- Return exactly one SELECT statement and nothing else, inside a ```sql code block.
- Use only the tables and columns in the schema below. Never invent columns.
- Always schema-qualify tables (e.g. public.orders).
- Prefer explicit JOINs on the foreign keys shown.
- Never modify data.

Schema:
{schema}"""


class ChatClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OpenAIChatClient:
    """Thin wrapper so the generator can be tested with a fake client."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return response.choices[0].message.content or ""


_CODE_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_sql(text: str) -> str:
    match = _CODE_BLOCK.search(text)
    return (match.group(1) if match else text).strip().rstrip(";").strip()


def generate_sql(
    question: str,
    schema: str,
    client: ChatClient,
    *,
    max_rows: int = 200,
    max_attempts: int = 2,
) -> str:
    """Ask the LLM for SQL, validate it, and give it one chance to fix a rejected query."""
    system = SYSTEM_PROMPT.format(schema=schema)
    prompt = question
    last_error: Exception | None = None
    for _ in range(max_attempts):
        sql = extract_sql(client.complete(system, prompt))
        try:
            return check_query(sql, max_rows).sql
        except UnsafeQueryError as exc:
            last_error = exc
            prompt = (
                f"{question}\n\nYour previous answer was rejected: {exc}\n"
                f"Previous SQL:\n{sql}\nReturn a corrected single SELECT statement."
            )
    raise UnsafeQueryError(f"Could not produce a safe query: {last_error}")
