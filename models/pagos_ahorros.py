from db.connection import get_connection

def get_all():
    """Get all savings payment tracking entries."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, ahorro_id, persona, mes, anio, pagado, updated_at
                FROM pagos_ahorros
                ORDER BY anio DESC, mes DESC, persona
            """)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def get_or_create_for_month(mes: int, anio: int):
    """Ensure a pagos_ahorros record exists for each (ahorro, persona) pair in the given month."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO pagos_ahorros (ahorro_id, persona, mes, anio, pagado)
                SELECT a.id, p.persona, %s, %s, FALSE
                FROM ahorros a
                CROSS JOIN (SELECT UNNEST(%s::varchar[]) AS persona) p
                ON CONFLICT (ahorro_id, persona, mes, anio) DO NOTHING
            """, (mes, anio, ["Marco", "Chiara"]))
            conn.commit()

            cur.execute("""
                SELECT id, ahorro_id, persona, mes, anio, pagado, updated_at
                FROM pagos_ahorros
                WHERE mes = %s AND anio = %s
                ORDER BY ahorro_id, persona
            """, (mes, anio))
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def toggle_pago(ahorro_id: int, persona: str, mes: int, anio: int, pagado: bool):
    """Toggle deposit status for a savings entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE pagos_ahorros
                SET pagado = %s, updated_at = NOW()
                WHERE ahorro_id = %s AND persona = %s AND mes = %s AND anio = %s
                RETURNING id, ahorro_id, persona, mes, anio, pagado, updated_at
            """, (pagado, ahorro_id, persona, mes, anio))
            cols = [desc[0] for desc in cur.description]
            result = cur.fetchone()
            conn.commit()
            return dict(zip(cols, result)) if result else None

def delete(row_id: int):
    """Delete a savings payment tracking entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pagos_ahorros WHERE id = %s", (row_id,))
            conn.commit()
