from db.connection import get_connection

def get_all():
    """Get all savings entries."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ahorro, total
                FROM ahorros
                ORDER BY ahorro
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict):
    """Insert a new savings entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ahorros (ahorro, total)
                VALUES (%s, %s)
                RETURNING id, ahorro, total
            """, (data["ahorro"], float(data["total"])))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """Update a savings entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ahorros
                SET ahorro = %s, total = %s
                WHERE id = %s
                RETURNING id, ahorro, total
            """, (data["ahorro"], float(data["total"]), row_id))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def delete(row_id: int):
    """Delete a savings entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ahorros WHERE id = %s", (row_id,))
            conn.commit()
