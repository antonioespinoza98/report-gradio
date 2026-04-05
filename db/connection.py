import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

_pool = None

def init_pool():
    """Initialize the connection pool from DATABASE_URL."""
    global _pool
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set")

    _pool = psycopg2.pool.ThreadedConnectionPool(1, 20, db_url)

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
