import os
import pathlib

import psycopg
import pytest

TEST_URL = os.getenv("PG_TEST_URL")


@pytest.fixture(scope="session")
def db_url():
    if not TEST_URL:
        pytest.skip("set PG_TEST_URL to run database tests")
    sql = (pathlib.Path(__file__).parents[1] / "examples" / "shop_schema.sql").read_text()
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(sql)
    return TEST_URL
