from db.connection import get_connection

_COLS = "id, nombre, destino, fecha_inicio, fecha_fin, created_at"

def get_all():
    """Get all trips, most recent first."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT {_COLS}
                FROM viajes
                ORDER BY fecha_inicio DESC, id DESC
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def find_by_fecha(fecha):
    """Get the trip whose date range contains fecha, or None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT {_COLS}
                FROM viajes
                WHERE %s BETWEEN fecha_inicio AND fecha_fin
                ORDER BY fecha_inicio DESC, id DESC
                LIMIT 1
            """, (fecha,))
            result = cur.fetchone()
            if not result:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, result))

def insert(data: dict):
    """Insert a new trip."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                INSERT INTO viajes (nombre, destino, fecha_inicio, fecha_fin)
                VALUES (%s, %s, %s, %s)
                RETURNING {_COLS}
            """, (
                data["nombre"],
                data.get("destino") or None,
                data["fecha_inicio"],
                data["fecha_fin"]
            ))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))
