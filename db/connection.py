import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

# psycopg2 maps NUMERIC to Decimal, which is not JSON-serializable. Gradio embeds
# each component's default value in the API schema it builds for "/", so a Decimal
# in any gr.Dataframe makes the whole page fail to render. Amounts here are money
# with 2 decimals, so float represents them exactly enough.
_DEC2FLOAT = psycopg2.extensions.new_type(
    psycopg2.extensions.DECIMAL.values,
    "DEC2FLOAT",
    lambda value, curs: float(value) if value is not None else None,
)
psycopg2.extensions.register_type(_DEC2FLOAT)

_pool = None

def init_pool():
    """Initialize the connection pool from DATABASE_URL."""
    global _pool
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    schema = os.getenv("DB_SCHEMA", "public")
    _pool = psycopg2.pool.ThreadedConnectionPool(1, 20, db_url, options=f"-c search_path={schema}")

@contextmanager
def get_connection():
    """Get a connection from the pool as a context manager."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call init_pool() first.")

    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)

def execute_sql_file(filepath: str):
    """Execute SQL statements from a file. Useful for schema initialization."""
    with open(filepath, 'r') as f:
        sql = f.read()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
