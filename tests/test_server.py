import pytest

from pg_mcp.config import Settings
from pg_mcp.server import build_server
from pg_mcp.sql_guard import UnsafeQueryError


class FakeLLM:
    def complete(self, system, user):
        assert "public.orders" in system  # live schema is passed to the model
        return "```sql\nSELECT c.name, count(*) AS orders FROM public.orders o JOIN public.customers c ON c.id = o.customer_id GROUP BY c.name ORDER BY orders DESC\n```"


async def test_tools_end_to_end(db_url):
    server = build_server(Settings(databases={"shop": db_url}), llm=FakeLLM())
    names = {t.name for t in await server.list_tools()}
    assert names == {"list_databases", "list_tables", "describe_table", "run_query", "explain_query", "ask"}

    result = await server.call_tool("ask", {"question": "Who ordered the most?"})
    data = result.structured_content
    assert data["rows"][0] == {"name": "Ayesha Khan", "orders": 2}


async def test_unsafe_sql_is_rejected(db_url):
    server = build_server(Settings(databases={"shop": db_url}))
    with pytest.raises(Exception) as info:
        await server.call_tool("run_query", {"sql": "DROP TABLE public.orders"})
    assert isinstance(info.value.__cause__, UnsafeQueryError)
