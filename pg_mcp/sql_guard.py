"""Static safety checks for SQL that an AI model wants to run.

Defence in depth: this guard rejects anything that is not a single read-only
query, and the database layer *also* runs every query inside a READ ONLY
transaction with a statement timeout. Either layer alone would block writes;
together they also block expensive or dangerous read-side functions.
"""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# Node types that can change data, schema, permissions or session state.
_FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,  # anything sqlglot can't model (COPY, VACUUM, DO blocks...)
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Into,  # SELECT ... INTO new_table
    exp.Copy,
)

# Functions that are read-only in name only: they sleep, touch the filesystem,
# reach other servers or change server state.
BLOCKED_FUNCTIONS = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "lo_get",
        "dblink",
        "dblink_exec",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "set_config",
        "pg_advisory_lock",
        "pg_advisory_xact_lock",
        "nextval",
        "setval",
        "query_to_xml",
        "pg_notify",
    }
)

_READ_ROOTS = (exp.Select, exp.Union, exp.Except, exp.Intersect)


class UnsafeQueryError(ValueError):
    """Raised when a query fails the safety checks."""


@dataclass(frozen=True)
class CheckedQuery:
    sql: str
    tables: tuple[str, ...]
    limit_applied: bool


def _function_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return (node.sql_name() or "").lower()


def check_query(sql: str, max_rows: int = 200) -> CheckedQuery:
    """Validate ``sql`` and return a version that is safe to execute.

    Rules:
      * exactly one statement
      * the statement is a SELECT (optionally with CTEs / set operations)
      * no data-modifying or DDL nodes anywhere, including inside CTEs
      * no blocked functions
      * a row LIMIT no larger than ``max_rows`` is always present
    """
    if not sql or not sql.strip():
        raise UnsafeQueryError("Query is empty.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as exc:
        raise UnsafeQueryError(f"Could not parse SQL: {exc.errors[0]['description'] if exc.errors else exc}") from exc

    if len(statements) != 1:
        raise UnsafeQueryError("Only one statement per call is allowed.")

    tree = statements[0]
    if not isinstance(tree, _READ_ROOTS):
        raise UnsafeQueryError(
            f"Only SELECT queries are allowed (got {tree.key.upper()})."
        )

    for node in tree.walk():
        if isinstance(node, _FORBIDDEN_NODES):
            raise UnsafeQueryError(f"{node.key.upper()} is not allowed in a read-only query.")
        if isinstance(node, exp.Func) and _function_name(node) in BLOCKED_FUNCTIONS:
            raise UnsafeQueryError(f"Function {_function_name(node)}() is not allowed.")
        if isinstance(node, exp.Lock):
            raise UnsafeQueryError("Row locking (FOR UPDATE/SHARE) is not allowed.")

    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}
    tables = tuple(
        sorted(
            {
                ".".join(p for p in (t.db, t.name) if p)
                for t in tree.find_all(exp.Table)
                if t.db or t.name not in cte_names
            }
        )
    )

    limit_applied = False
    current = tree.args.get("limit")
    current_value = None
    if isinstance(current, exp.Limit) and isinstance(current.expression, exp.Literal):
        try:
            current_value = int(current.expression.this)
        except ValueError:
            current_value = None

    if current_value is None or current_value > max_rows:
        simple_limit = current is None or current_value is not None
        if isinstance(tree, exp.Select) and simple_limit:
            tree = tree.limit(max_rows, copy=False)
        else:
            # Set operations or non-literal limits: wrap so the cap always applies.
            tree = exp.select("*").from_(tree.subquery("q")).limit(max_rows)
        limit_applied = True

    return CheckedQuery(sql=tree.sql(dialect="postgres"), tables=tables, limit_applied=limit_applied)
