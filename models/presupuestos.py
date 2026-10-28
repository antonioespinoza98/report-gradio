"""CRUD de la tabla presupuestos y consumo mensual por presupuesto."""

from decimal import Decimal, InvalidOperation

from db.connection import get_connection
from utils.constants import CATEGORIAS, RESPONSABLE_OPTIONS

_COLS = "id, nombre, categoria, monto_mensual, responsable"


def validar_presupuesto(data: dict) -> dict:
    """Normaliza y valida un presupuesto sin tocar la base.

    Devuelve un dict con `nombre`, `categoria`, `responsable` (str) y
    `monto_mensual` como Decimal con 2 decimales. Lanza ValueError con
    un mensaje en español si algo no es válido.
    """
    nombre = str(data.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El nombre del presupuesto no puede estar vacío.")

    categoria = str(data.get("categoria") or "").strip()
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoría no válida: «{categoria}».")

    responsable = str(data.get("responsable") or "").strip()
    if responsable not in RESPONSABLE_OPTIONS:
        raise ValueError(f"Responsable no válido: «{responsable}».")

    bruto = data.get("monto_mensual")
    if bruto is None or str(bruto).strip() == "":
        raise ValueError("El monto mensual es obligatorio.")
    try:
        # str() evita arrastrar el error binario si llega un float de Gradio.
        monto = Decimal(str(bruto)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Monto mensual no válido: «{bruto}».") from exc
    if not monto.is_finite() or monto < 0:
        raise ValueError("El monto mensual debe ser un número mayor o igual a 0.")

    return {
        "nombre": nombre,
        "categoria": categoria,
        "monto_mensual": monto,
        "responsable": responsable,
    }


def get_all() -> list[dict]:
    """Devuelve todos los presupuestos ordenados por nombre."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_COLS} FROM presupuestos ORDER BY nombre")
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def insert(data: dict) -> dict:
    """Inserta un presupuesto validado y lo devuelve."""
    p = validar_presupuesto(data)
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO presupuestos (nombre, categoria, monto_mensual, responsable)
                    VALUES (%s, %s, %s, %s)
                    RETURNING {_COLS}
                    """,
                    (p["nombre"], p["categoria"], p["monto_mensual"], p["responsable"]),
                )
                cols = [desc[0] for desc in cur.description]
                result = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return dict(zip(cols, result))


def update(row_id: int, data: dict) -> dict | None:
    """Actualiza un presupuesto; devuelve None si el id no existe."""
    p = validar_presupuesto(data)
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE presupuestos
                    SET nombre = %s, categoria = %s, monto_mensual = %s, responsable = %s
                    WHERE id = %s
                    RETURNING {_COLS}
                    """,
                    (p["nombre"], p["categoria"], p["monto_mensual"], p["responsable"], row_id),
                )
                cols = [desc[0] for desc in cur.description]
                result = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return dict(zip(cols, result)) if result else None


def delete(row_id: int) -> None:
    """Elimina un presupuesto por id."""
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM presupuestos WHERE id = %s", (row_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_consumo_mes(mes: int, anio: int) -> list[dict]:
    """Consumo de cada presupuesto en un mes (solo lectura, una consulta).

    `gastado` es la suma de gastos_variables.monto de la categoría del
    presupuesto, solo de tipo «Gasto Común» (los personales no consumen
    presupuesto), de cualquier persona, con fecha dentro del mes; 0.0 si
    no hubo gastos. Los retiros de un fondo (fondo_id no nulo) tampoco consumen
    presupuesto: los filtros van en el ON para no perder presupuestos sin gastos.
    `disponible` = monto_mensual - gastado (negativo si
    se superó el tope). Los NUMERIC llegan como float (db/connection.py).
    """
    if not 1 <= int(mes) <= 12:
        raise ValueError(f"Mes no válido: {mes}.")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH rango AS (
                    SELECT make_date(%(anio)s, %(mes)s, 1) AS inicio,
                           (make_date(%(anio)s, %(mes)s, 1) + INTERVAL '1 month')::date AS fin
                )
                SELECT p.id, p.nombre, p.categoria, p.monto_mensual, p.responsable,
                       COALESCE(SUM(g.monto), 0) AS gastado,
                       p.monto_mensual - COALESCE(SUM(g.monto), 0) AS disponible
                FROM presupuestos p
                CROSS JOIN rango r
                LEFT JOIN gastos_variables g
                       ON g.categoria = p.categoria
                      AND g.fecha >= r.inicio
                      AND g.fecha <  r.fin
                      AND g.fondo_id IS NULL
                      AND g.tipo_de_gasto = 'Gasto Común'
                GROUP BY p.id, p.nombre, p.categoria, p.monto_mensual, p.responsable
                ORDER BY p.nombre
                """,
                {"mes": int(mes), "anio": int(anio)},
            )
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # Cierra la transacción implícita de la lectura antes de devolver al pool.
        conn.commit()
        return rows
