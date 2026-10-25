from decimal import Decimal, InvalidOperation

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


def validar_saldo_inicial(saldo) -> Decimal:
    """Saldo de partida como Decimal con 2 decimales y >= 0 (función pura)."""
    if saldo is None or str(saldo).strip() == "":
        raise ValueError("El saldo actual del fondo es obligatorio.")
    try:
        # str() evita arrastrar el error binario si llega un float de Gradio.
        valor = Decimal(str(saldo)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Saldo no válido: «{saldo}».") from exc
    if not valor.is_finite() or valor < 0:
        raise ValueError("El saldo actual del fondo debe ser mayor o igual a 0.")
    return valor


def fijar_saldo_inicial(fondo_id: int, saldo) -> dict | None:
    """Fija el saldo de partida de un fondo y la fecha/hora de corte (NOW()).

    Desde ese momento el saldo = saldo_inicial + depósitos marcados después
    del corte − retiros registrados después del corte. Volver a llamarla
    mueve el corte: todo lo anterior queda absorbido en el nuevo saldo.
    Devuelve id, ahorro, total, saldo_inicial, fecha_corte; None si el fondo
    no existe.
    """
    valor = validar_saldo_inicial(saldo)
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE ahorros
                    SET saldo_inicial = %s, fecha_corte = NOW()
                    WHERE id = %s
                    RETURNING id, ahorro, total, saldo_inicial, fecha_corte
                """, (valor, fondo_id))
                cols = [desc[0] for desc in cur.description]
                result = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return dict(zip(cols, result)) if result else None
