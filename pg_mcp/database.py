"""PostgreSQL access layer. Every query runs in a READ ONLY transaction with a timeout."""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .sql_guard import CheckedQuery, check_query

_TABLES_SQL = """
SELECT t.table_schema, t.table_name, t.table_type,
       c.reltuples::bigint AS approx_rows,
       obj_description(c.oid) AS comment
FROM information_schema.tables t
JOIN pg_class c ON c.relname = t.table_name
JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = t.table_schema
WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
  AND (%(schema)s::text IS NULL OR t.table_schema = %(schema)s)
ORDER BY t.table_schema, t.table_name
"""

_COLUMNS_SQL = """
SELECT c.column_name, c.data_type, c.is_nullable = 'YES' AS nullable,
       c.column_default,
       col_description(format('%%I.%%I', c.table_schema, c.table_name)::regclass, c.ordinal_position) AS comment
FROM information_schema.columns c
WHERE c.table_schema = %(schema)s AND c.table_name = %(table)s
ORDER BY c.ordinal_position
"""

_CONSTRAINTS_SQL = """
SELECT tc.constraint_type, kcu.column_name,
       ccu.table_schema AS ref_schema, ccu.table_name AS ref_table, ccu.column_name AS ref_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_type = 'FOREIGN KEY' AND ccu.constraint_name = tc.constraint_name
WHERE tc.table_schema = %(schema)s AND tc.table_name = %(table)s
  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
"""


def _jsonable(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    return value


def split_table_name(name: str) -> tuple[str, str]:
    if "." in name:
        schema, table = name.split(".", 1)
        return schema, table
    return "public", name


class Database:
    def __init__(self, url: str, *, max_rows: int = 200, statement_timeout_ms: int = 5000):
        self.url = url
        self.max_rows = max_rows
        self.statement_timeout_ms = statement_timeout_ms

    @contextmanager
    def _read_only(self) -> Iterator[psycopg.Cursor]:
        with psycopg.connect(self.url, autocommit=False) as conn:
            conn.read_only = True
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT set_config('statement_timeout', %s, true)",
                    (str(self.statement_timeout_ms),),
                )
                try:
                    yield cur
                finally:
                    conn.rollback()

    def list_tables(self, schema: str | None = None) -> list[dict[str, Any]]:
        with self._read_only() as cur:
            cur.execute(_TABLES_SQL, {"schema": schema})
            return [{k: _jsonable(v) for k, v in row.items()} for row in cur.fetchall()]

    def describe_table(self, table: str) -> dict[str, Any]:
        schema, name = split_table_name(table)
        with self._read_only() as cur:
            cur.execute(_COLUMNS_SQL, {"schema": schema, "table": name})
            columns = cur.fetchall()
            if not columns:
                raise LookupError(f"Table {schema}.{name} not found")
            cur.execute(_CONSTRAINTS_SQL, {"schema": schema, "table": name})
            constraints = cur.fetchall()

        primary_key = [c["column_name"] for c in constraints if c["constraint_type"] == "PRIMARY KEY"]
        foreign_keys = [
            {
                "column": c["column_name"],
                "references": f'{c["ref_schema"]}.{c["ref_table"]}.{c["ref_column"]}',
            }
            for c in constraints
            if c["constraint_type"] == "FOREIGN KEY"
        ]
        return {
            "table": f"{schema}.{name}",
            "columns": [{k: _jsonable(v) for k, v in col.items()} for col in columns],
            "primary_key": primary_key,
            "foreign_keys": foreign_keys,
        }

    def schema_overview(self, schema: str | None = None) -> str:
        """Compact text description of all tables, used as LLM context."""
        lines: list[str] = []
        for t in self.list_tables(schema):
            info = self.describe_table(f'{t["table_schema"]}.{t["table_name"]}')
            cols = ", ".join(
                f'{c["column_name"]} {c["data_type"]}' + ("" if c["nullable"] else " not null")
                for c in info["columns"]
            )
            extras = []
            if info["primary_key"]:
                extras.append(f'pk({", ".join(info["primary_key"])})')
            extras += [f'{fk["column"]} -> {fk["references"]}' for fk in info["foreign_keys"]]
            suffix = f"  [{'; '.join(extras)}]" if extras else ""
            lines.append(f'{info["table"]}({cols}){suffix}')
        return "\n".join(lines)

    def run_query(self, sql: str) -> dict[str, Any]:
        checked: CheckedQuery = check_query(sql, self.max_rows)
        with self._read_only() as cur:
            cur.execute(checked.sql)
            rows = cur.fetchall()
            columns = [d.name for d in cur.description or []]
        return {
            "sql": checked.sql,
            "columns": columns,
            "rows": [{k: _jsonable(v) for k, v in r.items()} for r in rows],
            "row_count": len(rows),
            "truncated": checked.limit_applied and len(rows) == self.max_rows,
        }

    def explain(self, sql: str) -> list[str]:
        checked = check_query(sql, self.max_rows)
        with self._read_only() as cur:
            cur.execute("EXPLAIN " + checked.sql)
            return [row["QUERY PLAN"] for row in cur.fetchall()]
