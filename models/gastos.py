from db.connection import get_connection
from datetime import date

def get_all():
    """Get all variable expenses."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, created_at
                FROM gastos_variables
                ORDER BY fecha DESC, created_at DESC
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_last_n(n: int):
    """Get the last n variable expenses."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, created_at
                FROM gastos_variables
                ORDER BY fecha DESC, created_at DESC
                LIMIT %s
            """, (n,))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_filtered(persona=None, categoria=None, date_from=None, date_to=None):
    """Get filtered variable expenses."""
    query = "SELECT id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, created_at FROM gastos_variables WHERE 1=1"
    params = []

    if persona:
        query += " AND persona = %s"
        params.append(persona)
    if categoria:
        query += " AND categoria = %s"
        params.append(categoria)
    if date_from:
        query += " AND fecha >= %s"
        params.append(date_from)
    if date_to:
        query += " AND fecha <= %s"
        params.append(date_to)

    query += " ORDER BY fecha DESC, created_at DESC"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict):
    """Insert a new variable expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO gastos_variables (persona, descripcion, categoria, monto, fecha, tipo_de_gasto)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, created_at
            """, (
                data["persona"],
                data["descripcion"],
                data["categoria"],
                float(data["monto"]),
                data["fecha"],
                data.get("tipo_de_gasto", "Gasto Común")
            ))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """Update a variable expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE gastos_variables
                SET persona = %s, descripcion = %s, categoria = %s, monto = %s, fecha = %s, tipo_de_gasto = %s
                WHERE id = %s
                RETURNING id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, created_at
            """, (
                data["persona"],
                data["descripcion"],
                data["categoria"],
                float(data["monto"]),
                data["fecha"],
                data.get("tipo_de_gasto", "Gasto Común"),
                row_id
            ))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def delete(row_id: int):
    """Delete a variable expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM gastos_variables WHERE id = %s", (row_id,))
            conn.commit()
