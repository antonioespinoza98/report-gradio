"""Plan mensual: ingreso menos lo ASIGNADO a cada persona (réplica del Excel «Plan financiero»).

Lógica pura (sin base ni Gradio). Reglas:
- Ingreso por persona = suma de `ingresos.total`.
- Gastos fijos: monto de `gastos_fijos.total` (autoritativo), asignado a quien figure en
  `responsable_gastos` para ese gasto (cruce por nombre).
- Presupuestos: `presupuestos.monto_mensual` de la persona que figura como responsable
  del propio presupuesto.
- Aportes a ahorros: `responsable_gastos.monto` de las filas cuyo gasto es el nombre de un
  ahorro (puede diferir por persona, p. ej. Ahorro Común).
- Total asignado = fijos + presupuestos + ahorros. Sobrante = Ingreso − Total asignado.
- «Ambos» o sin responsable no se reparte: no se cuenta en nadie y se avisa.
- Si un nombre es a la vez gasto fijo y ahorro (p. ej. Drumming) cuenta solo como ahorro.
"""

import polars as pl

from utils.constants import PERSONAS
from utils.money import eur

COLUMNAS = ["Persona", "Ingreso", "Gastos fijos", "Presupuestos",
            "Aportes a ahorros", "Total asignado", "Sobrante"]
_EPS = 0.005


def _c(x) -> int:
    """Monto a céntimos enteros (suma exacta, sin deriva de float)."""
    return round(float(x or 0) * 100)


def _m(cent: int) -> float:
    """Céntimos a euros float redondeado, sin -0.0."""
    v = round(cent / 100, 2)
    return 0.0 if v == 0 else v


def _n(s) -> str:
    return (s or "").strip()


def calc_plan(
    ingresos_rows: list[dict],
    gastos_fijos_rows: list[dict],
    responsable_rows: list[dict],
    presupuestos_rows: list[dict],
    ahorros_rows: list[dict],
) -> tuple[pl.DataFrame, list[str]]:
    """Devuelve (DataFrame numérico por persona, lista de advertencias en español)."""
    avisos: list[str] = []
    sin_asignar = 0  # céntimos que no quedaron en nadie

    ing = {p: 0 for p in PERSONAS}
    for r in ingresos_rows:
        if r.get("persona") in ing:
            ing[r["persona"]] += _c(r.get("total"))

    fijos = {_n(r["gasto"]): _c(r.get("total")) for r in gastos_fijos_rows}
    ahorros = {_n(r["ahorro"]): _c(r.get("total")) for r in ahorros_rows}
    nombres_pres = {_n(r["nombre"]) for r in presupuestos_rows}

    # responsable_gastos agrupado por gasto
    resp_por_gasto: dict[str, list[tuple[str, int]]] = {}
    for r in responsable_rows:
        resp_por_gasto.setdefault(_n(r["gasto"]), []).append((_n(r.get("responsable")), _c(r.get("monto"))))

    tot_fijos = {p: 0 for p in PERSONAS}
    tot_pres = {p: 0 for p in PERSONAS}
    tot_ahor = {p: 0 for p in PERSONAS}

    # (b) nombres huérfanos
    conocidos = set(fijos) | set(ahorros) | nombres_pres
    for gasto in sorted(resp_por_gasto):
        if gasto not in conocidos:
            monto = sum(m for _, m in resp_por_gasto[gasto])
            avisos.append(
                f"⚠️ «{gasto}» está en Responsable de Gastos ({eur(_m(monto))}) pero no existe como "
                "gasto fijo, ahorro ni presupuesto (¿se renombró o se borró?). No se cuenta en el plan."
            )

    # Gastos fijos (un nombre que también es ahorro cuenta solo como ahorro)
    for gasto in sorted(fijos):
        total = fijos[gasto]
        if gasto in ahorros:
            avisos.append(
                f"⚠️ «{gasto}» figura a la vez como gasto fijo y como ahorro: en el plan cuenta solo "
                "como ahorro (aporte), para no contarlo doble."
            )
            continue
        filas = resp_por_gasto.get(gasto, [])
        personas = []
        for resp, _ in filas:
            if resp in tot_fijos and resp not in personas:
                personas.append(resp)
        if not personas:
            sin_asignar += total
            motivo = "es «Ambos»" if any(r == "Ambos" for r, _ in filas) else "no tiene responsable asignado"
            avisos.append(f"⚠️ El gasto fijo «{gasto}» ({eur(_m(total))}) {motivo}: no se reparte ni se cuenta en nadie.")
            continue
        if len(personas) > 1:
            avisos.append(
                f"⚠️ El gasto fijo «{gasto}» tiene varios responsables ({', '.join(personas)}): "
                "su total se cuenta completo en cada uno."
            )
        for p in personas:
            tot_fijos[p] += total

    # Presupuestos
    for r in presupuestos_rows:
        monto = _c(r.get("monto_mensual"))
        resp = _n(r.get("responsable"))
        if resp in tot_pres:
            tot_pres[resp] += monto
        else:
            sin_asignar += monto
            motivo = "es «Ambos»" if resp == "Ambos" else "no tiene responsable asignado"
            avisos.append(f"⚠️ El presupuesto «{_n(r['nombre'])}» ({eur(_m(monto))}) {motivo}: no se cuenta en nadie.")

    # Ahorros
    for ahorro in sorted(ahorros):
        total = ahorros[ahorro]
        filas = resp_por_gasto.get(ahorro, [])
        asignado = 0
        for resp, monto in filas:
            asignado += monto
            if resp in tot_ahor:
                tot_ahor[resp] += monto
            else:
                sin_asignar += monto
                avisos.append(f"⚠️ El aporte a «{ahorro}» de {eur(_m(monto))} está asignado a «{resp or 'nadie'}»: no se cuenta en ninguna persona.")
        if not filas:
            sin_asignar += total
            avisos.append(f"⚠️ El ahorro «{ahorro}» ({eur(_m(total))}) no tiene responsable asignado: no se cuenta en nadie.")
        elif asignado != total:
            dif = asignado - total
            detalle = " + ".join(f"{r or 'nadie'} {eur(_m(m))}" for r, m in filas)
            avisos.append(
                f"⚠️ Los aportes a «{ahorro}» suman {eur(_m(asignado))} ({detalle}) y el total del ahorro es "
                f"{eur(_m(total))}: diferencia de {eur(_m(abs(dif)))} ({'de más' if dif > 0 else 'de menos'})."
            )

    if sin_asignar:
        avisos.append(f"⚠️ En total quedaron sin asignar {eur(_m(sin_asignar))} (no están en el plan de nadie).")

    filas_out = []
    for p in PERSONAS:
        asignado = tot_fijos[p] + tot_pres[p] + tot_ahor[p]
        filas_out.append({
            "Persona": p,
            "Ingreso": _m(ing[p]),
            "Gastos fijos": _m(tot_fijos[p]),
            "Presupuestos": _m(tot_pres[p]),
            "Aportes a ahorros": _m(tot_ahor[p]),
            "Total asignado": _m(asignado),
            "Sobrante": _m(ing[p] - asignado),
        })
    df = pl.DataFrame(filas_out, schema={c: (pl.Utf8 if c == "Persona" else pl.Float64) for c in COLUMNAS})

    # (d) diferencia de sobrante (informativo)
    s = dict(zip(df["Persona"], df["Sobrante"]))
    a, b = PERSONAS
    if abs(s[a] - s[b]) >= _EPS:
        avisos.append(f"ℹ️ A {a} le sobran {eur(s[a])} y a {b} {eur(s[b])}: diferencia de {eur(abs(s[a] - s[b]))}.")
    return df, avisos


def conclusion_plan(df: pl.DataFrame) -> str:
    """Frase de conclusión generada desde los datos del plan."""
    if df.is_empty():
        return "No hay datos para armar el plan."
    s = dict(zip(df["Persona"], df["Sobrante"]))
    a, b = PERSONAS
    if abs(s[a] - s[b]) < _EPS:
        return f"Con el plan actual a {a} le sobran {eur(s[a])} y a {b} {eur(s[b])}: **sobra lo mismo a las dos**."
    mas = a if s[a] > s[b] else b
    return (f"Con el plan actual a {a} le sobran {eur(s[a])} y a {b} {eur(s[b])}: "
            f"la diferencia es de **{eur(abs(s[a] - s[b]))}** a favor de {mas}.")


def plan_para_mostrar(df: pl.DataFrame) -> pl.DataFrame:
    """Mismo plan con los montos como texto en euros (1.234,56 €)."""
    return df.with_columns([pl.col(c).map_elements(eur, return_dtype=pl.Utf8)
                            for c in COLUMNAS if c != "Persona"])


def avisos_markdown(avisos: list[str]) -> str:
    """Advertencias como lista Markdown; vacío si no hay."""
    if not avisos:
        return ""
    return "**Advertencias del plan**\n\n" + "\n".join(f"- {a}" for a in avisos)
