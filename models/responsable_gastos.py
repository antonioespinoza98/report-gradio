from db.connection import get_connection

def get_all():
    """Get all expense responsibility entries."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, gasto, responsable, monto
                FROM responsable_gastos
                ORDER BY gasto
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict):
    """Insert a new expense responsibility entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO responsable_gastos (gasto, responsable, monto)
                VALUES (%s, %s, %s)
                RETURNING id, gasto, responsable, monto
            """, (data["gasto"], data["responsable"], float(data["monto"])))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """Update an expense responsibility entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE responsable_gastos
                SET gasto = %s, responsable = %s, monto = %s
                WHERE id = %s
                RETURNING id, gasto, responsable, monto
            """, (data["gasto"], data["responsable"], float(data["monto"]), row_id))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def delete(row_id: int):
    """Delete an expense responsibility entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM responsable_gastos WHERE id = %s", (row_id,))
            conn.commit()
