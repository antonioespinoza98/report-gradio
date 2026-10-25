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

# Monto a depositar por (ahorro, persona): responsable_gastos con gasto = nombre del
# ahorro (sin espacios sobrantes, como el tracker) y responsable = persona. Solo vale
# si hay exactamente una fila; con 0 (o solo «Ambos») o varias, queda NULL.
_N_MONTOS = """
    (SELECT COUNT(*) FROM ahorros a
     JOIN responsable_gastos r ON btrim(r.gasto) = btrim(a.ahorro)
     WHERE a.id = p.ahorro_id AND r.responsable = p.persona)
"""
_MONTO_ACTUAL = """
    (SELECT CASE WHEN COUNT(*) = 1 THEN MIN(r.monto) END FROM ahorros a
     JOIN responsable_gastos r ON btrim(r.gasto) = btrim(a.ahorro)
     WHERE a.id = p.ahorro_id AND r.responsable = p.persona)
"""


def toggle_pago(ahorro_id: int, persona: str, mes: int, anio: int, pagado: bool) -> dict | None:
    """Marca o desmarca un depósito y guarda su monto, en una sola sentencia.

    Al marcar, `monto` = monto actual de responsable_gastos para ese ahorro y
    persona (NULL si no hay exactamente una fila); al desmarcar, NULL.
    updated_at = NOW() decide si el depósito cuenta después del corte del fondo.

    Devuelve la fila (id, ahorro_id, persona, mes, anio, pagado, monto,
    updated_at) más `n_montos` (filas encontradas en responsable_gastos) y
    `aviso` (str en español o None) para que la UI avise si se marcó sin
    monto. None si la fila del mes no existe.
    """
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE pagos_ahorros p
                    SET pagado = %(pagado)s,
                        updated_at = NOW(),
                        monto = CASE WHEN %(pagado)s THEN {_MONTO_ACTUAL} END
                    WHERE p.ahorro_id = %(ahorro_id)s AND p.persona = %(persona)s
                      AND p.mes = %(mes)s AND p.anio = %(anio)s
                    RETURNING p.id, p.ahorro_id, p.persona, p.mes, p.anio, p.pagado,
                              p.monto, p.updated_at, {_N_MONTOS} AS n_montos
                """, {
                    "pagado": bool(pagado), "ahorro_id": ahorro_id, "persona": persona,
                    "mes": mes, "anio": anio,
                })
                cols = [desc[0] for desc in cur.description]
                result = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if not result:
        return None
    fila = dict(zip(cols, result))
    fila["aviso"] = aviso_monto(fila)
    return fila


def aviso_monto(fila: dict) -> str | None:
    """Mensaje para la UI si un depósito quedó marcado sin monto (función pura)."""
    if not fila.get("pagado") or fila.get("monto") is not None:
        return None
    n = fila.get("n_montos") or 0
    motivo = (
        "no hay un monto para esa persona en Responsable de Gastos"
        if n == 0 else
        f"hay {n} filas para esa persona en Responsable de Gastos y no se sabe cuál usar"
    )
    return (
        f"Depósito de {fila.get('persona')} marcado sin monto: {motivo}. "
        "No suma al saldo del fondo hasta que se corrija y se vuelva a marcar."
    )


def delete(row_id: int):
    """Delete a savings payment tracking entry."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pagos_ahorros WHERE id = %s", (row_id,))
            conn.commit()
