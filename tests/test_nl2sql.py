import pytest

from pg_mcp.nl2sql import extract_sql, generate_sql
from pg_mcp.sql_guard import UnsafeQueryError


class FakeLLM:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def complete(self, system, user):
        self.prompts.append(user)
        return self.answers.pop(0)


def test_extract_sql_from_code_block():
    assert extract_sql("Here:\n```sql\nSELECT 1;\n```") == "SELECT 1"


def test_generate_returns_checked_sql():
    llm = FakeLLM("```sql\nSELECT name FROM public.customers\n```")
    assert generate_sql("list customers", "schema", llm, max_rows=20) == "SELECT name FROM public.customers LIMIT 20"


def test_generate_retries_after_rejection():
    llm = FakeLLM("```sql\nDELETE FROM public.customers\n```", "```sql\nSELECT 1\n```")
    assert generate_sql("q", "schema", llm).startswith("SELECT 1")
    assert "rejected" in llm.prompts[1]


def test_generate_gives_up():
    llm = FakeLLM("DROP TABLE x", "DROP TABLE x")
    with pytest.raises(UnsafeQueryError):
        generate_sql("q", "schema", llm)
