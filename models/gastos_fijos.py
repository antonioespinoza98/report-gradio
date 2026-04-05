from db.connection import get_connection

def get_all():
    """Get all fixed expenses."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, gasto, total
                FROM gastos_fijos
                ORDER BY gasto
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict):
    """Insert a new fixed expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO gastos_fijos (gasto, total)
                VALUES (%s, %s)
                RETURNING id, gasto, total
            """, (data["gasto"], float(data["total"])))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """Update a fixed expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE gastos_fijos
                SET gasto = %s, total = %s
                WHERE id = %s
                RETURNING id, gasto, total
            """, (data["gasto"], float(data["total"]), row_id))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def delete(row_id: int):
    """Delete a fixed expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM gastos_fijos WHERE id = %s", (row_id,))
            conn.commit()
