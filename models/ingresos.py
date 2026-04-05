from db.connection import get_connection

def get_all():
    """Get all income entries."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, tipo_ingreso, total, persona
                FROM ingresos
                ORDER BY persona, tipo_ingreso
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict):
    """Insert a new income entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ingresos (tipo_ingreso, total, persona)
                VALUES (%s, %s, %s)
                RETURNING id, tipo_ingreso, total, persona
            """, (data["tipo_ingreso"], float(data["total"]), data["persona"]))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """Update an income entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ingresos
                SET tipo_ingreso = %s, total = %s, persona = %s
                WHERE id = %s
                RETURNING id, tipo_ingreso, total, persona
            """, (data["tipo_ingreso"], float(data["total"]), data["persona"], row_id))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def delete(row_id: int):
    """Delete an income entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ingresos WHERE id = %s", (row_id,))
            conn.commit()
