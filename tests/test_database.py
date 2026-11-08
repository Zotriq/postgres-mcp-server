import psycopg
import pytest

from pg_mcp.database import Database


def test_list_and_describe(db_url):
    db = Database(db_url)
    names = {t["table_name"] for t in db.list_tables("public")}
    assert {"customers", "orders", "order_items", "products"} <= names

    info = db.describe_table("public.orders")
    assert info["primary_key"] == ["id"]
    assert {"column": "customer_id", "references": "public.customers.id"} in info["foreign_keys"]


def test_run_query_returns_rows(db_url):
    db = Database(db_url, max_rows=2)
    result = db.run_query("SELECT name, country FROM public.customers ORDER BY name")
    assert result["columns"] == ["name", "country"]
    assert result["row_count"] == 2
    assert result["truncated"] is True


def test_numeric_and_dates_are_json_friendly(db_url):
    result = Database(db_url).run_query("SELECT price, current_date AS d FROM public.products LIMIT 1")
    row = result["rows"][0]
    assert isinstance(row["price"], float)
    assert isinstance(row["d"], str)


def test_session_is_read_only_even_if_guard_is_bypassed(db_url):
    db = Database(db_url)
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with db._read_only() as cur:
            cur.execute("DELETE FROM public.order_items")


def test_statement_timeout(db_url):
    db = Database(db_url, statement_timeout_ms=100)
    with pytest.raises(psycopg.errors.QueryCanceled):
        with db._read_only() as cur:
            cur.execute("SELECT count(*) FROM generate_series(1, 300000000)")


def test_schema_overview_mentions_foreign_keys(db_url):
    text = Database(db_url).schema_overview("public")
    assert "public.orders(" in text
    assert "customer_id -> public.customers.id" in text
