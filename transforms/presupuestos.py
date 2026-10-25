"""Lógica pura del Panel de Control: estado, proyección y tarjetas de presupuestos.

No toca la base ni Gradio: recibe las filas de `models.presupuestos.get_consumo_mes`
(id, nombre, categoria, monto_mensual, responsable, gastado, disponible) y devuelve
estructuras listas para mostrar (dicts y HTML).

Reglas de negocio:
- `gastado` cuenta todos los gastos variables de la categoría, de cualquier persona.
- Estado: «excedido» si gastado > tope; «alerta» (a punto de excederse) si el consumo
  es >= 80 % del tope o la proyección a fin de mes supera el tope; si no, «ok».
- Proyección = gastado / días transcurridos × días del mes, solo en el mes en curso y a
  partir del día 4 (antes, un ritmo de 1-3 días no es representativo). En un mes ya
  cerrado la «proyección» es lo realmente gastado; en un mes futuro no hay proyección.
"""

import calendar
from collections import Counter
from datetime import date
from html import escape

from utils.money import eur, pct

UMBRAL_ALERTA = 80.0        # % del tope desde el cual se avisa
DIAS_MIN_PROYECCION = 4     # primer día del mes en que se proyecta

OK, ALERTA, EXCEDIDO = "ok", "alerta", "excedido"

# estado -> (ícono, texto, color de énfasis). El color nunca va solo: siempre con ícono y texto.
ESTADOS = {
    OK: ("✅", "OK", "#2e7d32"),
    ALERTA: ("⚠️", "A punto de excederse", "#e0a100"),
    EXCEDIDO: ("🔴", "Excedido", "#c62828"),
}

MENSAJE_SIN_PRESUPUESTOS = (
    "Todavía no hay presupuestos. Creálos en **Gastos Fijos > Presupuestos** "
    "(nombre, categoría, tope mensual y responsable)."
)
MENSAJE_SIN_TABLA = (
    "Todavía no existe la tabla de presupuestos: ejecutá la migración "
    "`db/migrations/001_presupuestos.sql` en la base y recargá."
)


def es_tabla_inexistente(exc: Exception) -> bool:
    """True si el error de la base es «relación no existe» (SQLSTATE 42P01)."""
    if getattr(exc, "pgcode", None) == "42P01":
        return True
    texto = str(exc).lower()
    return "presupuestos" in texto and "does not exist" in texto


def _r(valor: float) -> float:
    """Redondea a céntimos y evita -0.0 (equivalente escalar de utils.money.money)."""
    r = round(float(valor), 2)
    return 0.0 if r == 0 else r


def periodo_info(mes: int, anio: int, hoy: date) -> tuple[str, int, int]:
    """Devuelve (situación, días transcurridos, días del mes).

    situación: «en_curso», «cerrado» o «futuro».
    """
    dias_mes = calendar.monthrange(anio, mes)[1]
    if (anio, mes) == (hoy.year, hoy.month):
        return "en_curso", hoy.day, dias_mes
    if (anio, mes) < (hoy.year, hoy.month):
        return "cerrado", dias_mes, dias_mes
    return "futuro", 0, dias_mes


def proyectar(gastado: float, mes: int, anio: int, hoy: date) -> float | None:
    """Proyección a fin de mes por ritmo actual, o None si no corresponde proyectar."""
    situacion, dias, dias_mes = periodo_info(mes, anio, hoy)
    if situacion == "cerrado":
        return _r(gastado)
    if situacion == "futuro" or dias < DIAS_MIN_PROYECCION:
        return None
    return _r(float(gastado) / dias * dias_mes)


def porcentaje(gastado: float, tope: float) -> float | None:
    """% del tope consumido; None si el tope es 0 (no hay división posible)."""
    if not tope:
        return None
    return float(gastado) / float(tope) * 100


def estado_presupuesto(gastado: float, tope: float, proyeccion: float | None) -> str:
    """Clasifica en ok / alerta / excedido (ver reglas en el docstring del módulo)."""
    gastado, tope = float(gastado), float(tope)
    if gastado > tope:
        return EXCEDIDO
    p = porcentaje(gastado, tope)
    if p is not None and p >= UMBRAL_ALERTA:
        return ALERTA
    if proyeccion is not None and proyeccion > tope:
        return ALERTA
    return OK


def armar_tarjetas(filas: list[dict], mes: int, anio: int, hoy: date) -> list[dict]:
    """Convierte las filas de consumo en tarjetas con estado y proyección."""
    por_categoria = Counter(f["categoria"] for f in filas)
    tarjetas = []
    for f in filas:
        tope = _r(f["monto_mensual"])
        gastado = _r(f["gastado"] or 0)
        proy = proyectar(gastado, mes, anio, hoy)
        estado = estado_presupuesto(gastado, tope, proy)
        icono, texto, color = ESTADOS[estado]
        tarjetas.append({
            "nombre": f["nombre"],
            "categoria": f["categoria"],
            "responsable": f["responsable"],
            "tope": tope,
            "gastado": gastado,
            "restante": _r(tope - gastado),
            "pct": porcentaje(gastado, tope),
            "proyeccion": proy,
            "estado": estado,
            "icono": icono,
            "texto_estado": texto,
            "color": color,
            "comparte_categoria": por_categoria[f["categoria"]] > 1,
        })
    return tarjetas


def resumen_panel(tarjetas: list[dict]) -> dict:
    """Cuenta por estado y suma el sobrante proyectado.

    sobrante = Σ max(tope − proyección, 0). Si algún presupuesto no tiene proyección
    (primeros días del mes o mes futuro) el sobrante es None: sería una estimación vacía.
    """
    cuenta = Counter(t["estado"] for t in tarjetas)
    if not tarjetas or any(t["proyeccion"] is None for t in tarjetas):
        sobrante = None
    else:
        sobrante = _r(sum(max(t["tope"] - t["proyeccion"], 0) for t in tarjetas))
    return {
        "total": len(tarjetas),
        OK: cuenta[OK],
        ALERTA: cuenta[ALERTA],
        EXCEDIDO: cuenta[EXCEDIDO],
        "sobrante": sobrante,
    }


def titulo_resumen(res: dict, nombre_mes: str) -> str:
    """Título que dice la conclusión, generado a partir de los valores."""
    t = res["total"]
    if t == 0:
        return f"Presupuestos de {nombre_mes}"
    if res[EXCEDIDO]:
        return f"{res[EXCEDIDO]} de {t} presupuestos excedidos en {nombre_mes}"
    if res[ALERTA]:
        return f"{res[ALERTA]} de {t} presupuestos a punto de excederse en {nombre_mes}"
    return f"Los {t} presupuestos van dentro del tope en {nombre_mes}" if t > 1 else (
        f"El presupuesto va dentro del tope en {nombre_mes}")


def avisos_categoria(filas: list[dict], categoria: str) -> list[tuple[str, str]]:
    """Avisos al registrar un gasto: [(mensaje, nivel)] para cada presupuesto de la categoría.

    `filas` es el consumo del mes del gasto (ya incluye el gasto recién guardado).
    nivel: «info» si el consumo es < 80 % del tope, «warning» si es >= 80 % o excedido.
    """
    avisos = []
    for f in filas:
        if f["categoria"] != categoria:
            continue
        tope, gastado = _r(f["monto_mensual"]), _r(f["gastado"] or 0)
        p = porcentaje(gastado, tope)
        pct_txt = f" ({pct(p)})" if p is not None else ""
        base = f"{f['nombre']}: {eur(gastado)} de {eur(tope)}{pct_txt}"
        if gastado > tope:
            avisos.append((f"🔴 {base}. Superaste el tope por {eur(gastado - tope)}.", "warning"))
        elif p is not None and p >= UMBRAL_ALERTA:
            avisos.append((f"⚠️ {base}. Estás a punto de excederte.", "warning"))
        else:
            avisos.append((base, "info"))
    return avisos


def avisos_categoria_repetida(filas: list[dict]) -> list[str]:
    """Categorías con más de un presupuesto (el consumo se cuenta completo en cada uno)."""
    cuenta = Counter(f["categoria"] for f in filas)
    return [c for c, n in cuenta.items() if n > 1]


# ── HTML ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
.pc-fila{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0}
.pc-kpi{flex:1 1 170px;border:1px solid rgba(128,128,128,.35);border-radius:10px;padding:10px 14px}
.pc-kpi b{display:block;font-size:1.5em}
.pc-card{flex:1 1 280px;max-width:420px;border:1px solid rgba(128,128,128,.35);
 border-left-width:6px;border-radius:10px;padding:12px 14px}
.pc-card h4{margin:0 0 2px 0}
.pc-sub{opacity:.75;font-size:.9em}
.pc-barra{height:12px;border-radius:6px;background:rgba(128,128,128,.25);margin:10px 0 6px;overflow:hidden}
.pc-barra div{height:100%}
.pc-estado{font-weight:600}
.pc-nota{opacity:.8;font-size:.85em;margin-top:6px}
</style>
"""


def html_resumen(res: dict) -> str:
    """Fila de números clave: presupuestos por estado y sobrante proyectado."""
    kpis = []
    for estado in (OK, ALERTA, EXCEDIDO):
        icono, texto, color = ESTADOS[estado]
        kpis.append(
            f'<div class="pc-kpi" style="border-left:6px solid {color}">'
            f'<span>{icono} {escape(texto)}</span><b>{res[estado]}</b></div>'
        )
    if res["sobrante"] is None:
        valor = "—"
        nota = ("Se calcula a partir del día 4 del mes en curso." if res["total"]
                else "Sin presupuestos.")
    else:
        valor = eur(res["sobrante"])
        nota = "Debería ir al fondo de ahorro."
    kpis.append(
        '<div class="pc-kpi"><span>💰 Sobrante proyectado</span>'
        f'<b>{valor}</b><span class="pc-sub">{nota}</span></div>'
    )
    return _CSS + '<div class="pc-fila">' + "".join(kpis) + "</div>"


def _html_tarjeta(t: dict, situacion: str) -> str:
    p = t["pct"]
    ancho = 100 if (p is None and t["gastado"] > 0) else min(max(p or 0, 0), 100)
    pct_txt = pct(p) if p is not None else "—"
    if t["restante"] >= 0:
        restante = f"Restan <b>{eur(t['restante'])}</b>"
    else:
        restante = f"Excedido por <b>{eur(-t['restante'])}</b>"

    if situacion == "futuro":
        proy = "Mes futuro: sin datos."
    elif situacion == "cerrado":
        proy = f"Cierre del mes: <b>{eur(t['gastado'])}</b>"
    elif t["proyeccion"] is None:
        proy = f"Proyección disponible desde el día {DIAS_MIN_PROYECCION} del mes."
    else:
        proy = f"Proyección a fin de mes: <b>{eur(t['proyeccion'])}</b>"
        if t["proyeccion"] > t["tope"]:
            proy += f" (superaría el tope por {eur(t['proyeccion'] - t['tope'])})"

    nota = ""
    if t["comparte_categoria"]:
        nota = (f'<div class="pc-nota">La categoría «{escape(t["categoria"])}» tiene más de un '
                "presupuesto: el consumo se cuenta completo en cada uno.</div>")

    return (
        f'<div class="pc-card" style="border-left-color:{t["color"]}">'
        f'<h4>{escape(t["nombre"])}</h4>'
        f'<div class="pc-sub">Responsable: {escape(t["responsable"])} · {escape(t["categoria"])}</div>'
        f'<div class="pc-barra" role="progressbar" aria-valuenow="{ancho:.0f}" aria-valuemin="0" '
        f'aria-valuemax="100"><div style="width:{ancho:.1f}%;background:{t["color"]}"></div></div>'
        f'<div>{eur(t["gastado"])} de {eur(t["tope"])} ({pct_txt})</div>'
        f'<div>{restante}</div>'
        f'<div>{proy}</div>'
        f'<div class="pc-estado" style="color:{t["color"]}">{t["icono"]} {escape(t["texto_estado"])}</div>'
        f'{nota}</div>'
    )


def html_tarjetas(tarjetas: list[dict], mes: int, anio: int, hoy: date) -> str:
    """Una tarjeta por presupuesto, en rejilla fluida."""
    situacion = periodo_info(mes, anio, hoy)[0]
    return '<div class="pc-fila">' + "".join(_html_tarjeta(t, situacion) for t in tarjetas) + "</div>"
