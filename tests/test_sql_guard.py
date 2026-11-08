import pytest

from pg_mcp.sql_guard import UnsafeQueryError, check_query


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "UPDATE orders SET status = 'paid'",
        "INSERT INTO orders VALUES (1)",
        "DROP TABLE orders",
        "TRUNCATE orders",
        "CREATE TABLE x (id int)",
        "ALTER TABLE orders ADD COLUMN x int",
        "GRANT ALL ON orders TO public",
        "SELECT 1; DROP TABLE orders",
        "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
        "SELECT * INTO backup FROM orders",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM orders FOR UPDATE",
        "SELECT set_config('statement_timeout', '0', false)",
        "COPY orders TO '/tmp/out.csv'",
        "",
    ],
)
def test_rejects_unsafe(sql):
    with pytest.raises(UnsafeQueryError):
        check_query(sql)


def test_adds_limit_when_missing():
    q = check_query("SELECT * FROM public.orders", max_rows=50)
    assert q.sql.endswith("LIMIT 50")
    assert q.limit_applied
    assert q.tables == ("public.orders",)


def test_keeps_smaller_limit():
    q = check_query("SELECT * FROM orders LIMIT 5", max_rows=50)
    assert q.sql.endswith("LIMIT 5")
    assert not q.limit_applied


def test_caps_larger_limit():
    q = check_query("SELECT * FROM orders LIMIT 100000", max_rows=50)
    assert q.sql.endswith("LIMIT 50")


def test_wraps_set_operations():
    q = check_query("SELECT id FROM a UNION SELECT id FROM b", max_rows=10)
    assert q.sql.startswith("SELECT * FROM (")
    assert q.sql.endswith("LIMIT 10")


def test_allows_ctes_joins_and_aggregates():
    sql = """
    WITH spend AS (
        SELECT o.customer_id, SUM(p.price * oi.quantity) AS total
        FROM public.orders o
        JOIN public.order_items oi ON oi.order_id = o.id
        JOIN public.products p ON p.id = oi.product_id
        GROUP BY o.customer_id
    )
    SELECT c.name, s.total FROM spend s JOIN public.customers c ON c.id = s.customer_id
    ORDER BY s.total DESC
    """
    q = check_query(sql)
    assert set(q.tables) == {"public.orders", "public.order_items", "public.products", "public.customers"}
