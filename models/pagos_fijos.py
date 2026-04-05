from db.connection import get_connection

def get_all():
    """Get all fixed payment tracking entries."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, gasto_fijo_id, persona, mes, anio, pagado, updated_at
                FROM pagos_fijos
                ORDER BY anio DESC, mes DESC, persona
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_or_create_for_month(mes: int, anio: int):
    """Ensure a pago_fijo record exists for each (gasto_fijo, persona) pair in the given month."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Insert missing records (one for each gastos_fijos and each persona)
            cur.execute("""
                INSERT INTO pagos_fijos (gasto_fijo_id, persona, mes, anio, pagado)
                SELECT gf.id, p.persona, %s, %s, FALSE
                FROM gastos_fijos gf
                CROSS JOIN (SELECT UNNEST(%s::varchar[]) AS persona) p
                ON CONFLICT (gasto_fijo_id, persona, mes, anio) DO NOTHING
            """, (mes, anio, ["Marco", "Chiara"]))
            conn.commit()

            # Fetch all records for this month
            cur.execute("""
                SELECT id, gasto_fijo_id, persona, mes, anio, pagado, updated_at
                FROM pagos_fijos
                WHERE mes = %s AND anio = %s
                ORDER BY gasto_fijo_id, persona
            """, (mes, anio))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def toggle_pago(gasto_fijo_id: int, persona: str, mes: int, anio: int, pagado: bool):
    """Toggle payment status for a fixed expense."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pagos_fijos
                SET pagado = %s, updated_at = NOW()
                WHERE gasto_fijo_id = %s AND persona = %s AND mes = %s AND anio = %s
                RETURNING id, gasto_fijo_id, persona, mes, anio, pagado, updated_at
            """, (pagado, gasto_fijo_id, persona, mes, anio))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def insert(data: dict):
    """Insert a new payment tracking entry (rarely used; get_or_create_for_month is preferred)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pagos_fijos (gasto_fijo_id, persona, mes, anio, pagado)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, gasto_fijo_id, persona, mes, anio, pagado, updated_at
            """, (data["gasto_fijo_id"], data["persona"], data["mes"], data["anio"], data.get("pagado", False)))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result))

def delete(row_id: int):
    """Delete a payment tracking entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pagos_fijos WHERE id = %s", (row_id,))
            conn.commit()
