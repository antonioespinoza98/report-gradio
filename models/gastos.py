from db.connection import get_connection
from datetime import date
from decimal import Decimal, InvalidOperation

from utils.constants import CATEGORIAS, PERSONAS, TIPO_GASTO_OPTIONS

# Columns returned by every read. The LEFT JOINs keep rows without a trip/fondo intact.
# fondo_id/fondo_nombre: fondo con el que se pagó (NULL = gasto normal de caja).
# pagado_por: tal cual está en la base (NULL en filas viejas = lo pagó `persona`).
_SELECT = """
    SELECT g.id, g.persona, g.descripcion, g.categoria, g.monto, g.fecha,
           g.tipo_de_gasto, g.viaje_id, v.nombre AS viaje_nombre, g.created_at,
           g.fondo_id, f.ahorro AS fondo_nombre, g.pagado_por
    FROM gastos_variables g
    LEFT JOIN viajes v ON v.id = g.viaje_id
    LEFT JOIN ahorros f ON f.id = g.fondo_id
"""

_RETURNING = (
    "id, persona, descripcion, categoria, monto, fecha, tipo_de_gasto, viaje_id, created_at, "
    "fondo_id, pagado_por"
)


def _monto_decimal(bruto) -> Decimal:
    """Convierte un monto a Decimal con 2 decimales (> 0) o lanza ValueError."""
    if bruto is None or str(bruto).strip() == "":
        raise ValueError("El monto es obligatorio.")
    try:
        # str() evita arrastrar el error binario si llega un float de Gradio.
        monto = Decimal(str(bruto)).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"Monto no válido: «{bruto}».") from exc
    if not monto.is_finite() or monto <= 0:
        raise ValueError("El monto debe ser mayor que 0.")
    return monto


def _id_opcional(valor, campo: str) -> int | None:
    """None/"" -> None; si no, un entero positivo o ValueError."""
    if valor is None or str(valor).strip() == "":
        return None
    error = ValueError(f"{campo} no válido: «{valor}».")
    if isinstance(valor, bool):
        raise error
    if isinstance(valor, float):
        # Gradio puede entregar 3.0; 3.5 no es un id.
        if not valor.is_integer():
            raise error
        valor = int(valor)
    try:
        n = int(str(valor).strip())
    except ValueError as exc:
        raise error from exc
    if n <= 0:
        raise error
    return n


def _pagado_por(valor, persona: str) -> str:
    """Quién pagó: None/"" -> persona (quien registra); si no, Marco o Chiara."""
    if valor is None or str(valor).strip() == "":
        return persona
    valor = str(valor).strip()
    if valor not in PERSONAS:
        raise ValueError(f"«Pagado por» no válido: «{valor}».")
    return valor


def validar_gasto(data: dict) -> dict:
    """Normaliza y valida un gasto nuevo sin tocar la base.

    Devuelve un dict listo para insertar: `monto` como Decimal (> 0, 2
    decimales), `fecha` como date, `viaje_id`/`fondo_id` int o None y
    `pagado_por` en PERSONAS (por defecto, `persona`). Lanza ValueError
    con un mensaje en español si algo no es válido.
    """
    persona = str(data.get("persona") or "").strip()
    if persona not in PERSONAS:
        raise ValueError(f"Persona no válida: «{persona}».")

    descripcion = str(data.get("descripcion") or "").strip()
    if not descripcion:
        raise ValueError("La descripción no puede estar vacía.")

    categoria = str(data.get("categoria") or "").strip()
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoría no válida: «{categoria}».")

    tipo = str(data.get("tipo_de_gasto") or "Gasto Común").strip()
    if tipo not in TIPO_GASTO_OPTIONS:
        raise ValueError(f"Tipo de gasto no válido: «{tipo}».")

    fecha = data.get("fecha")
    if not isinstance(fecha, date):
        try:
            fecha = date.fromisoformat(str(fecha or "").strip())
        except ValueError as exc:
            raise ValueError(f"Fecha no válida (usá AAAA-MM-DD): «{data.get('fecha')}».") from exc

    return {
        "persona": persona,
        "descripcion": descripcion,
        "categoria": categoria,
        "tipo_de_gasto": tipo,
        "monto": _monto_decimal(data.get("monto")),
        "fecha": fecha,
        "viaje_id": _id_opcional(data.get("viaje_id"), "Viaje"),
        "fondo_id": _id_opcional(data.get("fondo_id"), "Fondo"),
        "pagado_por": _pagado_por(data.get("pagado_por"), persona),
    }


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

def get_filtered(persona=None, categoria=None, date_from=None, date_to=None, viaje_id=None,
                 fondo_id: int | None = None, excluir_retiros: bool = False):
    """Get filtered variable expenses.

    fondo_id: solo los retiros de ese fondo. excluir_retiros=True deja solo
    los gastos de caja (fondo_id NULL), p. ej. para el gasto variable del mes.
    """
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
    if fondo_id:
        query += " AND g.fondo_id = %s"
        params.append(fondo_id)
    if excluir_retiros:
        query += " AND g.fondo_id IS NULL"

    query += " ORDER BY g.fecha DESC, g.created_at DESC"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            cols = [desc[0] for desc in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

def insert(data: dict) -> dict:
    """Inserta un gasto validado con validar_gasto (ValueError si no es válido).

    viaje_id y fondo_id son opcionales (None = sin viaje / gasto de caja);
    pagado_por por defecto es `persona`.
    """
    g = validar_gasto(data)
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO gastos_variables
                        (persona, descripcion, categoria, monto, fecha, tipo_de_gasto,
                         viaje_id, fondo_id, pagado_por)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_RETURNING}
                """, (
                    g["persona"],
                    g["descripcion"],
                    g["categoria"],
                    g["monto"],  # Decimal: psycopg2 lo adapta a numeric sin pasar por float
                    g["fecha"],
                    g["tipo_de_gasto"],
                    g["viaje_id"],
                    g["fondo_id"],
                    g["pagado_por"],
                ))
                cols = [desc[0] for desc in cur.description]
                result = cur.fetchone()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return dict(zip(cols, result))

def update(row_id: int, data: dict):
    """
    Update a variable expense.

    viaje_id, fondo_id and pagado_por are only touched when the key is present in
    `data`, so callers that don't know about them (e.g. the table editors) can't
    wipe them. pagado_por None vuelve a «lo pagó quien lo registró».
    """
    sets = ["persona = %s", "descripcion = %s", "categoria = %s", "monto = %s", "fecha = %s", "tipo_de_gasto = %s"]
    params = [
        data["persona"],
        data["descripcion"],
        data["categoria"],
        _monto_decimal(data["monto"]),
        data["fecha"],
        data.get("tipo_de_gasto", "Gasto Común"),
    ]

    if "viaje_id" in data:
        sets.append("viaje_id = %s")
        params.append(data["viaje_id"])
    if "fondo_id" in data:
        sets.append("fondo_id = %s")
        params.append(_id_opcional(data["fondo_id"], "Fondo"))
    if "pagado_por" in data:
        pagado_por = data["pagado_por"]
        if pagado_por is not None and str(pagado_por).strip() != "":
            pagado_por = _pagado_por(pagado_por, data["persona"])
        else:
            pagado_por = None
        sets.append("pagado_por = %s")
        params.append(pagado_por)

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
