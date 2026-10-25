"""Fondos de ahorro: saldo, retiros y excesos (solo lectura).

Cada fila de `ahorros` es un fondo. Regla de saldo (db/migrations/002_fondos.sql):

    saldo = saldo_inicial
          + depósitos marcados (pagos_ahorros.pagado) con updated_at > fecha_corte
          − retiros (gastos_variables con fondo_id) con created_at > fecha_corte

Si fecha_corte es NULL (todavía no se cargó el saldo de partida desde la UI)
cuentan todos los depósitos marcados y todos los retiros, y se marca
`sin_saldo_inicial=True`. Un depósito marcado sin monto (NULL) suma 0 y se
cuenta en `depositos_sin_monto` para que la UI avise.

La regla está dos veces, a propósito: en SQL para get_saldos (sumas exactas
en numeric, una consulta) y en Python puro en recorrer_fondo (para los
excesos, que necesitan el recorrido cronológico). Ambas usan corte estricto
(«>») y deben dar el mismo saldo.

Los NUMERIC llegan como float (db/connection.py); los cálculos de Python se
hacen en Decimal y se devuelven como float redondeado a céntimos.
"""

from datetime import date, datetime
from decimal import Decimal

from db.connection import get_connection

_CENT = Decimal("0.01")

# Saldos por fondo. %(anio)s/%(mes)s/%(inicio)s/%(fin)s: mes actual.
# Empieza por «WITH dep AS (» a propósito: la verificación de solo lectura
# antepone CTE con VALUES que sombrean las tablas.
_SALDOS_SQL = """
WITH dep AS (
    SELECT p.ahorro_id,
           SUM(p.monto) FILTER (
               WHERE a.fecha_corte IS NULL OR p.updated_at > a.fecha_corte
           ) AS depositos_periodo,
           COUNT(*) FILTER (
               WHERE p.monto IS NULL AND (a.fecha_corte IS NULL OR p.updated_at > a.fecha_corte)
           ) AS depositos_sin_monto,
           SUM(p.monto) FILTER (
               WHERE p.anio = %(anio)s AND p.mes = %(mes)s
           ) AS depositos_mes
    FROM pagos_ahorros p
    JOIN ahorros a ON a.id = p.ahorro_id
    WHERE p.pagado
    GROUP BY p.ahorro_id
),
ret AS (
    SELECT g.fondo_id,
           SUM(g.monto) FILTER (
               WHERE a.fecha_corte IS NULL OR g.created_at > a.fecha_corte
           ) AS retiros_periodo,
           SUM(g.monto) FILTER (
               WHERE g.fecha >= %(inicio)s AND g.fecha < %(fin)s
           ) AS retiros_mes
    FROM gastos_variables g
    JOIN ahorros a ON a.id = g.fondo_id
    GROUP BY g.fondo_id
)
SELECT a.id,
       a.ahorro AS nombre,
       a.total AS aporte_mensual,
       a.saldo_inicial,
       a.fecha_corte,
       (a.fecha_corte IS NULL) AS sin_saldo_inicial,
       COALESCE(d.depositos_periodo, 0) AS depositos_periodo,
       COALESCE(r.retiros_periodo, 0) AS retiros_periodo,
       a.saldo_inicial + COALESCE(d.depositos_periodo, 0) - COALESCE(r.retiros_periodo, 0) AS saldo,
       COALESCE(d.depositos_mes, 0) AS depositos_mes,
       COALESCE(r.retiros_mes, 0) AS retiros_mes,
       COALESCE(d.depositos_sin_monto, 0) AS depositos_sin_monto
FROM ahorros a
LEFT JOIN dep d ON d.ahorro_id = a.id
LEFT JOIN ret r ON r.fondo_id = a.id
ORDER BY a.ahorro
"""

# Retiros (gastos pagados con un fondo). pagado_por ya resuelto: NULL = persona.
_RETIROS_SQL = """
SELECT g.id, g.fondo_id, a.ahorro AS fondo_nombre, g.descripcion, g.categoria,
       g.monto, g.fecha, g.created_at, g.persona,
       COALESCE(g.pagado_por, g.persona) AS pagado_por,
       (a.fecha_corte IS NULL OR g.created_at > a.fecha_corte) AS cuenta_en_saldo
FROM gastos_variables g
JOIN ahorros a ON a.id = g.fondo_id
"""

_LIMITE_MAX = 1000


def _d(valor) -> Decimal:
    """float/Decimal/None -> Decimal en céntimos (None = 0)."""
    if valor is None:
        return Decimal("0.00")
    return Decimal(str(valor)).quantize(_CENT)


def _f(valor: Decimal) -> float:
    """Decimal -> float para Gradio/Plotly, sin -0.0."""
    return float(valor.quantize(_CENT)) + 0.0


def _rango_mes(hoy: date) -> tuple[date, date]:
    inicio = hoy.replace(day=1)
    fin = date(inicio.year + 1, 1, 1) if inicio.month == 12 else date(inicio.year, inicio.month + 1, 1)
    return inicio, fin


def _en_periodo(momento: datetime, fecha_corte: datetime | None) -> bool:
    """Misma regla que el SQL: sin corte cuenta todo; con corte, estrictamente después."""
    return fecha_corte is None or momento > fecha_corte


def recorrer_fondo(
    saldo_inicial,
    fecha_corte: datetime | None,
    depositos: list[dict],
    retiros: list[dict],
) -> dict:
    """Calcula saldo y excesos de UN fondo (función pura, sin SQL).

    depositos: filas de pagos_ahorros con `monto` (None = sin monto, suma 0),
      `updated_at` (cuándo se marcó) y opcionalmente `id` y `pagado`
      (si viene False, se ignora).
    retiros: filas de gastos_variables con `id`, `monto`, `created_at`, y
      para el informe `fecha`, `descripcion`, `persona`, `pagado_por`.

    Recorre cronológicamente los movimientos posteriores al corte (o todos si
    fecha_corte es None). Orden: momento, luego depósitos antes que retiros
    en el mismo instante, luego id. Cuando un retiro deja el saldo por debajo
    de 0, la parte que pasa de 0 es exceso; si el saldo ya era <= 0, todo el
    retiro es exceso. Un depósito posterior recupera el saldo pero no borra
    los excesos ya registrados.

    Devuelve dict con saldo_inicial, sin_saldo_inicial, depositos_periodo,
    retiros_periodo, depositos_sin_monto, saldo (floats salvo los flags/
    conteos) y `excesos`: lista de dicts con gasto_id, fecha, created_at,
    descripcion, persona, pagado_por, monto_retiro, exceso, saldo_antes,
    saldo_despues.
    """
    # Igual que el SQL: siempre se suma saldo_inicial (sin corte vale 0 por DEFAULT).
    inicial = _d(saldo_inicial)
    movimientos = []
    sin_monto = 0
    for dep in depositos:
        if dep.get("pagado") is False or not _en_periodo(dep["updated_at"], fecha_corte):
            continue
        if dep.get("monto") is None:
            sin_monto += 1
        movimientos.append((dep["updated_at"], 0, dep.get("id") or 0, "deposito", dep))
    for ret in retiros:
        if not _en_periodo(ret["created_at"], fecha_corte):
            continue
        movimientos.append((ret["created_at"], 1, ret.get("id") or 0, "retiro", ret))
    movimientos.sort(key=lambda m: m[:3])

    saldo = inicial
    total_dep = Decimal("0.00")
    total_ret = Decimal("0.00")
    excesos = []
    for momento, _, _, tipo, fila in movimientos:
        monto = _d(fila.get("monto"))
        if tipo == "deposito":
            saldo += monto
            total_dep += monto
            continue
        antes = saldo
        saldo -= monto
        total_ret += monto
        if saldo < 0:
            # min() cubre los dos casos: si antes > 0 es la parte que pasa de 0;
            # si antes <= 0, -saldo >= monto y el exceso es todo el retiro.
            exceso = min(monto, -saldo)
            excesos.append({
                "gasto_id": fila.get("id"),
                "fecha": fila.get("fecha"),
                "created_at": momento,
                "descripcion": fila.get("descripcion"),
                "persona": fila.get("persona"),
                "pagado_por": fila.get("pagado_por") or fila.get("persona"),
                "monto_retiro": _f(monto),
                "exceso": _f(exceso),
                "saldo_antes": _f(antes),
                "saldo_despues": _f(saldo),
            })

    return {
        "saldo_inicial": _f(inicial),
        "sin_saldo_inicial": fecha_corte is None,
        "depositos_periodo": _f(total_dep),
        "retiros_periodo": _f(total_ret),
        "depositos_sin_monto": sin_monto,
        "saldo": _f(saldo),
        "excesos": excesos,
    }


def get_saldos(hoy: date | None = None) -> list[dict]:
    """Saldo de cada fondo, ordenado por nombre (una consulta, solo lectura).

    Claves: id, nombre, aporte_mensual (ahorros.total), saldo_inicial,
    fecha_corte (datetime con zona o None), sin_saldo_inicial (bool),
    depositos_periodo, retiros_periodo (desde el corte), saldo,
    depositos_mes (marcados del mes actual del tracker, mes/anio de `hoy`),
    retiros_mes (retiros con fecha en el mes de `hoy`), depositos_sin_monto
    (int). depositos_mes/retiros_mes son el movimiento del mes, sin mirar el
    corte. hoy: por defecto date.today() (como el resto de la app).
    """
    hoy = hoy or date.today()
    inicio, fin = _rango_mes(hoy)
    params = {"anio": hoy.year, "mes": hoy.month, "inicio": inicio, "fin": fin}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_SALDOS_SQL, params)
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # Cierra la transacción implícita de la lectura antes de devolver al pool.
        conn.commit()
    return rows


def get_retiros(fondo_id: int | None = None, limit: int = 50) -> list[dict]:
    """Últimos retiros (más recientes primero por created_at), de un fondo o de todos.

    Claves: id, fondo_id, fondo_nombre, descripcion, categoria, monto, fecha,
    created_at, persona (quien lo registró), pagado_por (resuelto: si es NULL
    en la base, = persona), cuenta_en_saldo (bool: registrado después del
    corte o fondo sin corte).
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Límite no válido: «{limit}».") from exc
    if not 1 <= limit <= _LIMITE_MAX:
        raise ValueError(f"El límite debe estar entre 1 y {_LIMITE_MAX}.")

    query = _RETIROS_SQL
    params: list = []
    if fondo_id is not None:
        query += " WHERE g.fondo_id = %s"
        params.append(int(fondo_id))
    query += " ORDER BY g.created_at DESC, g.id DESC LIMIT %s"
    params.append(limit)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.commit()
    return rows


def get_excesos() -> list[dict]:
    """Excesos de todos los fondos desde su corte, en orden cronológico.

    Cada dict: fondo_id, fondo_nombre y las claves de recorrer_fondo()["excesos"]
    (gasto_id, fecha, created_at, descripcion, persona, pagado_por,
    monto_retiro, exceso, saldo_antes, saldo_despues). Tres consultas de
    lectura en una conexión; el recorrido se hace en recorrer_fondo.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, ahorro, saldo_inicial, fecha_corte FROM ahorros ORDER BY ahorro")
            fondos = cur.fetchall()
            cur.execute("""
                SELECT id, ahorro_id, monto, updated_at
                FROM pagos_ahorros
                WHERE pagado
            """)
            depositos = cur.fetchall()
            cur.execute("""
                SELECT id, fondo_id, monto, fecha, created_at, descripcion, persona, pagado_por
                FROM gastos_variables
                WHERE fondo_id IS NOT NULL
            """)
            cols_ret = [desc[0] for desc in cur.description]
            retiros = [dict(zip(cols_ret, row)) for row in cur.fetchall()]
        conn.commit()

    dep_por_fondo: dict[int, list[dict]] = {}
    for dep_id, ahorro_id, monto, updated_at in depositos:
        dep_por_fondo.setdefault(ahorro_id, []).append(
            {"id": dep_id, "monto": monto, "updated_at": updated_at}
        )
    ret_por_fondo: dict[int, list[dict]] = {}
    for ret in retiros:
        ret_por_fondo.setdefault(ret["fondo_id"], []).append(ret)

    excesos = []
    for fondo_id, nombre, saldo_inicial, fecha_corte in fondos:
        res = recorrer_fondo(
            saldo_inicial, fecha_corte,
            dep_por_fondo.get(fondo_id, []), ret_por_fondo.get(fondo_id, []),
        )
        for e in res["excesos"]:
            excesos.append({"fondo_id": fondo_id, "fondo_nombre": nombre, **e})
    excesos.sort(key=lambda e: (e["created_at"], e["gasto_id"] or 0))
    return excesos
