"""Lógica pura del tracker mensual de pagos (gastos fijos y ahorros).

Reproduce la regla de "N/A" que usaban los mapas de calor retirados: si
`responsable_gastos` indica quién es responsable de un concepto (cruce por
nombre) y la persona no está en ese conjunto, no le corresponde pagarlo.
"""
import polars as pl
from utils.constants import PERSONAS

PAGADO = "✅"
PENDIENTE = "⬜"
NO_APLICA = "N/A"


def responsables_por_nombre(responsable_rows: list[dict] | None) -> dict[str, set]:
    """Devuelve {nombre_concepto: {personas responsables}}.

    Acepta varias filas por el mismo concepto y expande "Ambos".
    """
    resp: dict[str, set] = {}
    for r in responsable_rows or []:
        key = (r.get("gasto") or "").strip()
        if not key:
            continue
        resp.setdefault(key, set())
        if r.get("responsable") == "Ambos":
            resp[key].update(PERSONAS)
        else:
            resp[key].add(r.get("responsable"))
    return resp


def aplica(nombre: str, persona: str, resp: dict[str, set]) -> bool:
    """False solo si se sabe quién es responsable y la persona no está."""
    responsables = resp.get(nombre.strip())
    return not (responsables and persona not in responsables)


def estado_tracker(
    pagos_rows: list[dict],
    items_rows: list[dict],
    id_col: str,
    name_col: str,
    responsable_rows: list[dict] | None,
    verbo: str = "Pagados",
) -> dict:
    """Arma el estado del tracker de un mes.

    pagos_rows: filas del mes (pagos_fijos / pagos_ahorros).
    items_rows: gastos_fijos / ahorros (con `id` y `name_col`).
    id_col: columna de pagos que apunta al ítem (gasto_fijo_id / ahorro_id).

    Devuelve dict con:
      nombres: list[str] ordenada
      ids: {nombre: id}
      choices: {persona: [nombres que le corresponden]}
      pagados: {persona: [nombres que le corresponden y están pagados]}
      tabla: pl.DataFrame (name_col capitalizado, Marco, Chiara) con ✅/⬜/N/A
      progreso: str "Pagados: X de Y ..."
    """
    ids = {r[name_col]: r["id"] for r in items_rows}
    nombres = sorted(ids)
    resp = responsables_por_nombre(responsable_rows)

    pagado_por = {(r[id_col], r["persona"]): bool(r["pagado"]) for r in pagos_rows}

    choices = {p: [n for n in nombres if aplica(n, p, resp)] for p in PERSONAS}
    pagados = {
        p: [n for n in choices[p] if pagado_por.get((ids[n], p), False)]
        for p in PERSONAS
    }

    columna = name_col.capitalize()
    tabla_dict: dict[str, list] = {columna: nombres}
    for p in PERSONAS:
        tabla_dict[p] = [
            NO_APLICA if n not in choices[p]
            else (PAGADO if n in pagados[p] else PENDIENTE)
            for n in nombres
        ]
    tabla = pl.DataFrame(tabla_dict, schema={columna: pl.Utf8, **{p: pl.Utf8 for p in PERSONAS}})

    total = sum(len(choices[p]) for p in PERSONAS)
    hechos = sum(len(pagados[p]) for p in PERSONAS)
    if total == 0:
        progreso = "Sin conceptos para este mes."
    else:
        detalle = " · ".join(f"{p} {len(pagados[p])} de {len(choices[p])}" for p in PERSONAS)
        progreso = f"**{verbo}: {hechos} de {total}** ({detalle})"

    return {
        "nombres": nombres,
        "ids": ids,
        "choices": choices,
        "pagados": pagados,
        "tabla": tabla,
        "progreso": progreso,
    }
