"""Lógica pura de los fondos de ahorro: tarjetas, avisos, excesos y su gráfico.

No toca la base ni Gradio. Recibe las filas de `models.fondos` (get_saldos,
get_retiros, get_excesos) y de `models.ahorros.get_all`, y devuelve dicts,
DataFrames, HTML y figuras de Plotly listos para mostrar.

Reglas (el cálculo del saldo vive en models/fondos.py; aquí solo se presenta):
- Estado del fondo: 🔴 negativo (saldo < 0), ⚠️ bajo (0 <= saldo < aporte mensual),
  ✅ positivo. Un fondo sin saldo de partida (sin corte) se marca aparte: su saldo
  es aproximado porque faltan los fondos que ya tenía antes de usar la app.
- Un retiro es un gasto pagado con el fondo. Si deja el saldo bajo 0, la parte
  que pasa de 0 es «exceso» y lo pagó (`pagado_por`) quien lo compró.
- El sistema no registra reposiciones: el exceso mostrado es el acumulado desde
  el corte de cada fondo y un depósito posterior no lo descuenta.
"""

from collections import defaultdict
from datetime import date, datetime
from html import escape

import plotly.graph_objects as go
import polars as pl

from transforms.presupuestos import _CSS as _CSS_BASE
from utils.constants import PERSONAS
from utils.money import eur

# Valor del desplegable «Pagado con fondo» cuando no se usa ningún fondo.
NINGUNO = 0
NINGUNO_LABEL = "Ninguno"

POSITIVO, BAJO, NEGATIVO = "positivo", "bajo", "negativo"

# estado -> (ícono, texto, color). El color nunca va solo: siempre con ícono y texto.
ESTADOS = {
    POSITIVO: ("✅", "Saldo positivo", "#2e7d32"),
    BAJO: ("⚠️", "Saldo bajo (menos de un aporte mensual)", "#e0a100"),
    NEGATIVO: ("🔴", "Saldo negativo", "#c62828"),
}

# Paleta apta para daltonismo (Okabe-Ito): azul y naranja; distinguibles sin depender del rojo/verde.
COLORES_PERSONA = {"Marco": "#0072B2", "Chiara": "#E69F00"}
_COLOR_TEXTO = {"Marco": "white", "Chiara": "black"}
_COLOR_OTRO = "#999999"
_COLOR_CUBIERTO = "#B0B7C3"  # gris neutro: lo que el fondo sí cubrió

MENSAJE_SIN_FONDOS = (
    "Todavía no hay fondos. Cada ahorro de **Gastos Fijos > Ahorros** es un fondo: "
    "creá uno y cargá su saldo actual."
)
MENSAJE_SIN_RETIROS = "Todavía no hay gastos pagados con fondo. Cuando registres uno, aparecerá aquí."
NOTA_EXCESOS = (
    "Solo cuentan los gastos pagados con fondo registrados después de cargar el saldo del fondo. "
    "El exceso es lo que un gasto pasó del saldo disponible, pagado de su bolsillo por quien se "
    "indica. «Por reponer» no descuenta reposiciones: el sistema no las registra, así que no "
    "resta lo que ya se haya devuelto ni los depósitos posteriores."
)

# Aviso único sobre los límites del cálculo del saldo (lo muestran Panel, Ahorros y Resumen del Mes).
AVISO_SALDO_TITULO = "⚠️ Cómo se calcula el saldo de un fondo (y sus límites)"
AVISO_SALDO_TEXTO = """\
**La regla.** Al cargar el saldo actual de un fondo, esa cifra ya incluye todo lo anterior. Desde ese \
momento se **suman los depósitos marcados** y se **restan los gastos pagados con fondo** que registres \
después.

**Puede contar doble en estos casos:**
- **Marcar, desmarcar y volver a marcar.** Si volvés a marcar un depósito después de cargar el saldo, \
cuenta como nuevo.
- **Marcar tarde un depósito que ya estaba en la cuenta.** Miraste el saldo el 25/10 y el depósito de \
junio ya estaba en la cuenta: si lo marcás el 26/10, se suma otra vez. Si el dinero entró recién el \
26/10, está bien.
- **Registrar tarde un gasto con fecha anterior.** Ya habías sacado ese dinero de la cuenta el 20/10 y \
miraste el saldo el 25/10: si lo registrás el 26/10, se resta otra vez.

**Consejo.** Antes de cargar el saldo actual, dejá al día las marcas de depósitos y los gastos pagados \
con fondo; después cargá el saldo. Si algo queda raro, volvé a cargar el saldo actual desde \
**Gastos Fijos > Ahorros**: eso mueve el punto de partida.

**Otros límites.** Los excesos se recalculan con los datos actuales (editar o borrar un gasto los \
cambia) y «por reponer» no descuenta reposiciones. El nombre del ahorro debe coincidir con el de \
**Responsable de Gastos**; si no, los depósitos quedan sin monto.
"""

_CSS_EXTRA = """
<style>
.pc-saldo{font-size:1.9em;font-weight:700;margin:6px 0 2px}
.pc-etiqueta{display:inline-block;font-size:.8em;font-weight:600;border:1px solid currentColor;
 border-radius:6px;padding:0 6px;margin-left:6px}
.pc-retiros{margin:8px 0 0 0;padding-left:18px;font-size:.9em}
</style>
"""

def _r(valor) -> float:
    """Redondea a céntimos y evita -0.0."""
    r = round(float(valor or 0), 2)
    return 0.0 if r == 0 else r


def fmt_fecha(valor) -> str:
    """date/datetime -> dd/mm/aaaa; None -> «—»."""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    return str(valor) if valor else "—"


def estado_fondo(saldo: float, aporte_mensual: float) -> str:
    """Clasifica el saldo: negativo, bajo (< 1 aporte mensual) o positivo."""
    saldo = _r(saldo)
    if saldo < 0:
        return NEGATIVO
    if aporte_mensual and saldo < _r(aporte_mensual):
        return BAJO
    return POSITIVO


# ── Tarjetas del Panel de Control ──────────────────────────────────────────────

def armar_tarjetas(saldos: list[dict], retiros: list[dict], max_retiros: int = 3) -> list[dict]:
    """Une el saldo de cada fondo con sus últimos retiros (los más recientes primero).

    `retiros` viene de models.fondos.get_retiros (ya ordenado de más reciente a
    más antiguo); se toman los `max_retiros` primeros de cada fondo.
    """
    por_fondo: dict[int, list[dict]] = defaultdict(list)
    for r in retiros:
        if len(por_fondo[r["fondo_id"]]) < max_retiros:
            por_fondo[r["fondo_id"]].append(r)

    tarjetas = []
    for s in saldos:
        saldo = _r(s["saldo"])
        aporte = _r(s["aporte_mensual"])
        estado = estado_fondo(saldo, aporte)
        icono, texto, color = ESTADOS[estado]
        tarjetas.append({
            "id": s["id"],
            "nombre": s["nombre"],
            "saldo": saldo,
            "aporte": aporte,
            "depositos_mes": _r(s["depositos_mes"]),
            "retiros_mes": _r(s["retiros_mes"]),
            "sin_saldo_inicial": bool(s["sin_saldo_inicial"]),
            "depositos_sin_monto": int(s.get("depositos_sin_monto") or 0),
            "estado": estado,
            "icono": icono,
            "texto_estado": texto,
            "color": color,
            "ultimos_retiros": por_fondo.get(s["id"], []),
        })
    return tarjetas


def titulo_fondos(tarjetas: list[dict]) -> str:
    """Título que dice la conclusión, generado a partir de los estados."""
    n = len(tarjetas)
    if n == 0:
        return "Fondos de ahorro"
    neg = sum(t["estado"] == NEGATIVO for t in tarjetas)
    bajo = sum(t["estado"] == BAJO for t in tarjetas)
    if neg:
        return f"{neg} de {n} fondos con saldo negativo"
    if bajo:
        return f"{bajo} de {n} fondos con saldo bajo"
    return f"Los {n} fondos tienen saldo positivo" if n > 1 else "El fondo tiene saldo positivo"


def aviso_sin_saldo(tarjetas: list[dict]) -> str:
    """Aviso persistente si algún fondo no tiene saldo de partida; '' si no."""
    nombres = [f"«{t['nombre']}»" for t in tarjetas if t["sin_saldo_inicial"]]
    if not nombres:
        return ""
    return (
        f"⚠️ Sin saldo de partida: {', '.join(nombres)}. Su saldo es aproximado: falta cargar el "
        "saldo actual en **Gastos Fijos > Ahorros** (sección «Saldo actual del fondo»)."
    )


def _linea_retiro(r: dict) -> str:
    texto = (f"{fmt_fecha(r['fecha'])} · {escape(str(r['descripcion']))} · "
             f"<b>{eur(r['monto'])}</b> · pagó {escape(str(r['pagado_por']))}")
    if r.get("cuenta_en_saldo") is False:
        texto += " (anterior al corte: no resta del saldo)"
    return f"<li>{texto}</li>"


def _html_tarjeta(t: dict) -> str:
    etiqueta = ""
    if t["sin_saldo_inicial"]:
        etiqueta = '<span class="pc-etiqueta">sin saldo de partida</span>'
    notas = ""
    if t["sin_saldo_inicial"]:
        notas += ('<div class="pc-nota">Saldo aproximado: falta cargar el saldo actual del fondo '
                  "(Gastos Fijos &gt; Ahorros).</div>")
    if t["depositos_sin_monto"]:
        notas += (f'<div class="pc-nota">{t["depositos_sin_monto"]} depósito(s) marcado(s) sin monto: '
                  "no suman al saldo.</div>")
    if t["ultimos_retiros"]:
        items = "".join(_linea_retiro(r) for r in t["ultimos_retiros"])
        retiros = f'<div class="pc-sub">Últimos retiros</div><ul class="pc-retiros">{items}</ul>'
    else:
        retiros = '<div class="pc-sub">Sin retiros registrados.</div>'
    return (
        f'<div class="pc-card" style="border-left-color:{t["color"]}">'
        f'<h4>{escape(t["nombre"])}{etiqueta}</h4>'
        '<div class="pc-sub">Saldo actual</div>'
        f'<div class="pc-saldo" style="color:{t["color"]}">{eur(t["saldo"])}</div>'
        f'<div class="pc-estado" style="color:{t["color"]}">{t["icono"]} {escape(t["texto_estado"])}</div>'
        f'<div>Depósitos del mes: <b>{eur(t["depositos_mes"])}</b> · '
        f'Retiros del mes: <b>{eur(t["retiros_mes"])}</b></div>'
        f'<div>Aporte mensual: <b>{eur(t["aporte"])}</b></div>'
        f'{notas}{retiros}</div>'
    )


def html_tarjetas(tarjetas: list[dict]) -> str:
    """Una tarjeta por fondo, en rejilla fluida (incluye el CSS para no depender de otra sección)."""
    return (_CSS_BASE + _CSS_EXTRA + '<div class="pc-fila">'
            + "".join(_html_tarjeta(t) for t in tarjetas) + "</div>")


# ── Aviso al registrar un retiro ───────────────────────────────────────────────

def avisos_retiro(fondo: dict | None, monto: float, pagado_por: str) -> list[tuple[str, str]]:
    """Avisos tras guardar un gasto pagado con un fondo: [(mensaje, nivel)].

    `fondo` es la fila de get_saldos leída DESPUÉS de guardar: su saldo ya resta
    este retiro (el gasto recién creado es posterior al corte), así que no se
    vuelve a restar. `monto` solo sirve para calcular cuánto del retiro fue
    exceso: si el saldo previo era positivo, la parte que pasa de 0; si ya era
    <= 0, todo el retiro. nivel: «info» o «warning».
    """
    if not fondo:
        return []
    nombre, saldo, monto = fondo["nombre"], _r(fondo["saldo"]), _r(monto)
    aprox = ""
    if fondo.get("sin_saldo_inicial"):
        aprox = " Saldo aproximado: falta cargar el saldo actual del fondo."
    if saldo < 0:
        exceso = min(monto, -saldo)
        previo = " El fondo ya estaba en negativo." if saldo + monto < 0 else ""
        return [(
            f"🔴 Exceso de {eur(exceso)} sobre el fondo «{nombre}», pagado por {pagado_por}: "
            f"queda por reponer. Saldo del fondo: {eur(saldo)}.{previo}{aprox}",
            "warning",
        )]
    return [(f"Fondo «{nombre}»: saldo de {eur(saldo)} tras este retiro.{aprox}",
             "warning" if aprox else "info")]


# ── Gasto pagado con fondo: cubierto y exceso ─────────────────────────────────

def desglosar_retiros(retiros: list[dict], excesos: list[dict]) -> list[dict]:
    """Une cada retiro con su exceso: cubierto = monto − exceso.

    `retiros` (get_retiros) trae `id`, `fondo_nombre`, `monto`, `fecha`,
    `descripcion`, `cuenta_en_saldo`; `excesos` (get_excesos) trae `gasto_id`,
    `fondo_nombre`, `exceso`, `pagado_por`, `monto_retiro`. Se ignoran los
    retiros anteriores al corte (`cuenta_en_saldo` False): ya están dentro del
    saldo de partida y no pueden dar exceso. Un exceso sin su retiro (p. ej. por
    el límite de filas de get_retiros) se agrega con los datos del propio exceso.
    Devuelve dicts: fondo, fecha, descripcion, monto, cubierto, exceso, pagado_por.
    """
    exc_por_id = {e["gasto_id"]: e for e in excesos if e.get("gasto_id") is not None}
    filas, vistos = [], set()
    for r in retiros:
        if r.get("cuenta_en_saldo") is False:
            continue
        e = exc_por_id.get(r["id"])
        monto = _r(r["monto"])
        exceso = min(_r(e["exceso"]), monto) if e else 0.0
        vistos.add(r["id"])
        filas.append({
            "fondo": r["fondo_nombre"], "fecha": r["fecha"], "descripcion": r["descripcion"],
            "monto": monto, "cubierto": _r(monto - exceso), "exceso": exceso,
            "pagado_por": (e["pagado_por"] or e["persona"]) if e else (r.get("pagado_por") or r.get("persona")),
        })
    for gid, e in exc_por_id.items():
        if gid not in vistos:
            exceso = _r(e["exceso"])
            monto = max(_r(e["monto_retiro"]), exceso)
            filas.append({
                "fondo": e["fondo_nombre"], "fecha": e["fecha"], "descripcion": e["descripcion"],
                "monto": monto, "cubierto": _r(monto - exceso), "exceso": exceso,
                "pagado_por": e["pagado_por"] or e["persona"],
            })
    return filas


def _exceso_por_persona(filas: list[dict]) -> dict[str, float]:
    tot: dict[str, float] = defaultdict(float)
    for f in filas:
        if f["exceso"] > 0:
            tot[f["pagado_por"]] += f["exceso"]
    return {p: _r(v) for p, v in tot.items()}


def titulo_gasto_fondo(filas: list[dict]) -> str:
    """Título con la conclusión: quién pagó cuánto de exceso, o que el fondo cubrió todo."""
    if not filas:
        return MENSAJE_SIN_RETIROS
    total = _r(sum(f["monto"] for f in filas))
    tot = _exceso_por_persona(filas)
    if not tot:
        return f"El fondo cubrió los {eur(total)} gastados con fondos: sin excesos"
    por_reponer = _r(sum(tot.values()))
    orden = sorted(tot.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(orden) == 1:
        p, v = orden[0]
        return f"Solo {p} pagó exceso: {eur(v)} por reponer, de {eur(total)} gastados con fondos"
    texto = f"{orden[0][0]} pagó {eur(orden[0][1])} de exceso y {orden[1][0]} {eur(orden[1][1])}"
    for p, v in orden[2:]:
        texto += f" y {p} {eur(v)}"
    return f"{texto}: {eur(por_reponer)} por reponer"


def _detalle_hover(items: list[tuple[dict, float]], max_items: int = 5) -> str:
    """Hasta `max_items` líneas «fecha · descripción: € » de los mayores, más «y N más»."""
    items = sorted(items, key=lambda it: -it[1])
    lineas = [f"{fmt_fecha(f['fecha'])} · {escape(str(f['descripcion'] or '—'))[:40]}: {eur(v)}"
              for f, v in items[:max_items]]
    if len(items) > max_items:
        lineas.append(f"y {len(items) - max_items} más")
    return "<br>".join(lineas)


def figura_gasto_fondo(filas: list[dict]) -> go.Figure | None:
    """Barras horizontales por fondo: gasto pagado con fondo apilado en cubierto + exceso por persona.

    Un fondo por barra (hay pocos): se ve de un vistazo cuánto se gastó con cada
    uno y qué parte tuvo que poner cada persona. Hover con el € de cada tramo y
    el detalle (fecha, descripción) de los gastos que lo componen. None si no hay filas.
    """
    if not filas:
        return None
    por_fondo: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        por_fondo[f["fondo"]].append(f)
    totales = {n: _r(sum(f["monto"] for f in fs)) for n, fs in por_fondo.items()}
    fondos = sorted(por_fondo, key=lambda n: (-totales[n], n))

    tramos = [("Cubierto por el fondo", _COLOR_CUBIERTO, "black",
               lambda f: f["cubierto"] if f["cubierto"] > 0 else 0.0)]
    personas = [p for p in PERSONAS if any(f["exceso"] > 0 and f["pagado_por"] == p for f in filas)]
    personas += sorted({f["pagado_por"] for f in filas if f["exceso"] > 0} - set(personas))
    for p in personas:
        tramos.append((f"Exceso pagado por {p}", COLORES_PERSONA.get(p, _COLOR_OTRO),
                       _COLOR_TEXTO.get(p, "black"),
                       lambda f, p=p: f["exceso"] if f["pagado_por"] == p else 0.0))

    fig = go.Figure()
    for nombre, color, color_texto, valor in tramos:
        xs, textos, hovers = [], [], []
        for n in fondos:
            items = [(f, valor(f)) for f in por_fondo[n] if valor(f) > 0]
            v = _r(sum(x for _, x in items))
            xs.append(v)
            textos.append(eur(v) if v > 0 else "")
            hovers.append(f"<b>{escape(n)}</b><br>{nombre}: <b>{eur(v)}</b><br>"
                          f"{_detalle_hover(items)}" if items else "")
        fig.add_bar(
            y=fondos, x=xs, orientation="h", name=nombre, marker_color=color,
            text=textos, textposition="inside", insidetextanchor="middle",
            textfont=dict(color=color_texto), customdata=hovers,
            hovertemplate="%{customdata}<extra></extra>",
        )
    for n in fondos:
        fig.add_annotation(x=totales[n], y=n, text=f"<b>{eur(totales[n])}</b>", showarrow=False,
                           xanchor="left", xshift=6)
    fig.update_layout(
        barmode="stack", separators=",.", height=max(240, 130 + 60 * len(fondos)),
        margin=dict(l=10, r=10, t=40, b=40),
        legend=dict(orientation="h", y=1.18, x=0),
        xaxis=dict(title="Gastado con el fondo (€)", tickformat=",.0f", ticksuffix=" €",
                   range=[0, max(totales.values()) * 1.25], rangemode="tozero"),
        yaxis=dict(autorange="reversed", title=None),
    )
    return fig


# ── Gastos Fijos > Ahorros (lista de fondos con su saldo) ─────────────────────

_COLS_AHORROS = {
    "Ahorro": pl.Utf8, "Aporte mensual": pl.Utf8, "Saldo actual": pl.Utf8,
    "Saldo de partida": pl.Utf8, "Fecha de corte": pl.Utf8, "Estado": pl.Utf8,
}


def combinar_ahorros(ahorros_rows: list[dict], saldos: list[dict] | None) -> list[dict]:
    """Une `ahorros.get_all` (id, ahorro, total) con `get_saldos`. saldos=None: no se pudo leer."""
    por_id = {s["id"]: s for s in (saldos or [])}
    filas = []
    for a in ahorros_rows:
        s = por_id.get(a["id"])
        filas.append({
            "id": a["id"],
            "ahorro": a["ahorro"],
            "total": a["total"],
            "saldo": s["saldo"] if s else None,
            "saldo_inicial": s["saldo_inicial"] if s else None,
            "fecha_corte": s["fecha_corte"] if s else None,
            "sin_saldo_inicial": bool(s["sin_saldo_inicial"]) if s else None,
        })
    return filas


def tabla_ahorros(filas: list[dict]) -> pl.DataFrame:
    """Tabla de solo lectura de fondos con saldos formateados."""
    def estado(f):
        if f["sin_saldo_inicial"] is None:
            return "—"
        return "⚠️ sin saldo de partida" if f["sin_saldo_inicial"] else "✅ con saldo de partida"
    return pl.DataFrame({
        "Ahorro": [f["ahorro"] for f in filas],
        "Aporte mensual": [eur(f["total"]) for f in filas],
        "Saldo actual": [eur(f["saldo"]) for f in filas],
        "Saldo de partida": [eur(f["saldo_inicial"]) if not f["sin_saldo_inicial"] else "—" for f in filas],
        "Fecha de corte": [fmt_fecha(f["fecha_corte"]) for f in filas],
        "Estado": [estado(f) for f in filas],
    }, schema=_COLS_AHORROS)


def aviso_ahorros(filas: list[dict], error: str | None = None) -> str:
    """Texto persistente bajo la tabla: error de lectura de saldos o fondos sin saldo de partida."""
    if error:
        return error
    nombres = [f"«{f['ahorro']}»" for f in filas if f["sin_saldo_inicial"]]
    if not nombres:
        return ""
    return (f"⚠️ Sin saldo de partida: {', '.join(nombres)}. Mientras no lo cargues, el saldo es "
            "aproximado. Elegí el fondo y usá «Saldo actual del fondo».")


def detalle_fondo(fila: dict | None) -> str:
    """Datos de solo lectura del fondo elegido (saldo actual, de partida y corte)."""
    if not fila:
        return "Elegí un fondo existente para ver su saldo."
    if fila["sin_saldo_inicial"] is None:
        return "Saldo no disponible (no se pudo leer)."
    if fila["sin_saldo_inicial"]:
        return (f"**Saldo actual:** {eur(fila['saldo'])} (aproximado) · **Saldo de partida:** sin cargar · "
                "**Corte:** —")
    return (f"**Saldo actual:** {eur(fila['saldo'])} · **Saldo de partida:** {eur(fila['saldo_inicial'])} · "
            f"**Corte:** {fmt_fecha(fila['fecha_corte'])}")
