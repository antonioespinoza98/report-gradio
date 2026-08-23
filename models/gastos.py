from db.connection import get_connection
from datetime import date

# Columns returned by every read. The LEFT JOIN keeps rows without a trip intact.
_SELECT = """
    SELECT g.id, g.persona, g.descripcion, g.categoria, g.monto, g.fecha,
           g.tipo_de_gasto, g.viaje_id, v.nombre AS viaje_nombre, g.created_at
    FROM gastos_variables g
    LEFT JOIN viajes v ON v.id = g.viaje_id
"""

_RETURNING = "id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, viaje_id, created_at"

def get_all():
    """Get all variable expenses."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {_SELECT}
                ORDER BY g.fecha DESC, g.created_at DESC
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_last_n(n: int):
    """Get the last n variable expenses."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                {_SELECT}
                ORDER BY g.fecha DESC, g.created_at DESC
                LIMIT %s
            """, (n,))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_filtered(persona=None, categoria=None, date_from=None, date_to=None, viaje_id=None):
    """Get filtered variable expenses."""
    query = f"{_SELECT} WHERE 1=1"
    params = []

    if persona:
        query += " AND g.persona = %s"
        params.append(persona)
    if categoria:
        query += " AND g.categoria = %s"
        params.append(categoria)
    if date_from:
        query += " AND g.fecha >= %s"
        params.append(date_from)
    if date_to:
        query += " AND g.fecha <= %s"
        params.append(date_to)
    if viaje_id:
        query += " AND g.viaje_id = %s"
        params.append(viaje_id)

    query += " ORDER BY g.fecha DESC, g.created_at DESC"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict):
    """Insert a new variable expense. viaje_id is optional (None = sin viaje)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO gastos_variables (persona, descripcion, categoria, monto, fecha, tipo_de_gasto, viaje_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING {_RETURNING}
            """, (
                data["persona"],
                data["descripcion"],
                data["categoria"],
                float(data["monto"]),
                data["fecha"],
                data.get("tipo_de_gasto", "Gasto Común"),
                data.get("viaje_id")
            ))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """
    Update a variable expense.

    viaje_id is only touched when the key is present in `data`, so callers that
    don't know about trips (e.g. the table editors) can't wipe the tag.
    """
    sets = ["persona = %s", "descripcion = %s", "categoria = %s", "monto = %s", "fecha = %s", "tipo_de_gasto = %s"]
    params = [
        data["persona"],
        data["descripcion"],
        data["categoria"],
        float(data["monto"]),
        data["fecha"],
        data.get("tipo_de_gasto", "Gasto Común"),
    ]

    if "viaje_id" in data:
        sets.append("viaje_id = %s")
        params.append(data["viaje_id"])

    params.append(row_id)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE gastos_variables
                SET {", ".join(sets)}
                WHERE id = %s
                RETURNING {_RETURNING}
            """, params)
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
