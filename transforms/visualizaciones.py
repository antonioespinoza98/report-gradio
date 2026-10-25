"""Gráficos, tarjetas y textos de la pestaña Visualizaciones (General y por categoría).

Todo es lógica pura: recibe filas de `gastos_variables` (lista de dicts) y los filtros
compartidos (persona, tipo de gasto, rango de fechas) y devuelve figuras Plotly o
Markdown. Las filas deben traer a AMBAS personas: las comparaciones (lo registrado por
cada uno, mezcla de categorías) ignoran a propósito el filtro de persona y lo avisan.

Ojo con el significado: `persona` en `gastos_variables` es quien REGISTRÓ el gasto, no quien
lo aporta ni quien es responsable (los presupuestos se ingresan como gastos variables). Los
textos hablan de «registrado» y nunca de aporte o peso.
"""
from datetime import date, timedelta

import plotly.graph_objects as go
import polars as pl

from utils.constants import PERSONAS, TIPO_GASTO_OPTIONS
from utils.money import eur, money, pct

# --------------------------------------------------------------------------
# Opciones de filtros y constantes
# --------------------------------------------------------------------------

PERSONA_OPCIONES = ["Ambos"] + PERSONAS
PERIODOS = ["Este mes", "Últimos 3 meses", "Todo"]
TIPO_TODOS = "Todos"
TIPO_OPCIONES = [TIPO_TODOS] + TIPO_GASTO_OPTIONS

MIN_MESES_TENDENCIA = 3  # con menos meses completos no hay promedio ni tendencia
SIN_CATEGORIA = "Sin categoría"
CATEGORIAS_DUDOSAS = ("Otros", SIN_CATEGORIA)

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
NOTA_REGISTRADO = (
    "«Registrado» no es lo mismo que «aportado»: la persona es quien anotó el gasto. Los "
    "presupuestos (p. ej. Supermercado) se ingresan como gastos variables, así que estas cifras "
    "no miden cuánto aporta ni de qué es responsable cada uno."
)

# Paleta apta para daltonismo (plotly.colors.qualitative.Safe).
COLOR_PERSONA = {"Marco": "#332288", "Chiara": "#AA4499"}
COLOR_SERIE = {
    ("Marco", "Gasto Común"): "#332288",
    ("Marco", "Gasto Personal"): "#88CCEE",
    ("Chiara", "Gasto Común"): "#AA4499",
    ("Chiara", "Gasto Personal"): "#DDCC77",
}
GRIS = "#B8BEC6"
GRIS_OSCURO = "#5F6670"
OPACIDAD_NO_COMPLETO = 0.55

_COLUMNAS = {
    "fecha": pl.Date, "persona": pl.Utf8, "tipo_de_gasto": pl.Utf8,
    "categoria": pl.Utf8, "monto": pl.Float64,
}


# --------------------------------------------------------------------------
# Fechas y formato
# --------------------------------------------------------------------------

def _parse_date(d):
    """Convierte 'YYYY-MM-DD' o date en date (None si no se puede)."""
    if d is None:
        return None
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except ValueError:
        return None


def _fmt_fecha(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _suma_meses(d: date, n: int) -> date:
    """Primer día del mes que está `n` meses después del mes de `d`."""
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, 1)


def _mes_fin(mes: date) -> date:
    return _suma_meses(mes, 1) - timedelta(days=1)


def _etq_mes(mes: date) -> str:
    return f"{MESES[mes.month - 1]} {mes.year}"


def _meses_entre(a: date, b: date) -> list[date]:
    out, m = [], a
    while m <= b:
        out.append(m)
        m = _suma_meses(m, 1)
    return out


def _eur0(v) -> str:
    """Euros sin decimales cuando son exactos (etiquetas compactas)."""
    return eur(v).replace(",00 €", " €")


def rango_periodo(periodo: str, hoy: date | None = None) -> tuple[date | None, date | None]:
    """Atajo de periodo -> (desde, hasta). 'Todo' devuelve (None, None).

    'Últimos 3 meses' = los 3 meses calendario completos anteriores + el mes en curso.
    """
    hoy = hoy or date.today()
    if periodo == "Este mes":
        return hoy.replace(day=1), hoy
    if periodo == "Últimos 3 meses":
        return _suma_meses(hoy, -3), hoy
    return None, None


# --------------------------------------------------------------------------
# Datos
# --------------------------------------------------------------------------

def _a_df(rows: list[dict]) -> pl.DataFrame:
    """Filas de la base -> DataFrame con solo las columnas usadas y tipos fijos."""
    if not rows:
        return pl.DataFrame(schema=_COLUMNAS)
    datos = [{k: r.get(k) for k in _COLUMNAS} for r in rows]
    df = pl.DataFrame(datos, infer_schema_length=None)
    return df.with_columns([pl.col(k).cast(t) for k, t in _COLUMNAS.items()]).with_columns(
        pl.when(pl.col("categoria").is_null() | (pl.col("categoria").str.strip_chars() == ""))
        .then(pl.lit(SIN_CATEGORIA)).otherwise(pl.col("categoria")).alias("categoria")
    )


def _vista(rows, tipo, desde, hasta) -> pl.DataFrame:
    """Filas filtradas por tipo de gasto y por el rango de fechas [desde, hasta]."""
    df = _a_df(rows)
    if tipo and tipo != TIPO_TODOS:
        df = df.filter(pl.col("tipo_de_gasto") == tipo)
    if hasta:
        df = df.filter(pl.col("fecha") <= hasta)
    if desde:
        df = df.filter(pl.col("fecha") >= desde)
    return df


def _de_persona(df: pl.DataFrame, persona: str) -> pl.DataFrame:
    return df if persona == "Ambos" else df.filter(pl.col("persona") == persona)


def _suma(df: pl.DataFrame) -> float:
    return round(float(df["monto"].sum() or 0.0), 2)


def _estado_mes(mes: date, hoy: date, desde, hasta) -> str:
    """'Completo', 'En curso' (contiene hoy) o 'Parcial' (recortado por el filtro)."""
    fin = _mes_fin(mes)
    if fin < hoy and (hasta is None or fin <= hasta) and (desde is None or mes >= desde):
        return "Completo"
    if mes <= hoy <= fin:
        return "En curso"
    return "Parcial"


_SUFIJO_ESTADO = {"Completo": "", "En curso": " (en curso)", "Parcial": " (parcial)"}


# --------------------------------------------------------------------------
# Piezas de figura
# --------------------------------------------------------------------------

def _quien(persona: str) -> str:
    return "Marco y Chiara" if persona == "Ambos" else persona


def _subtitulo(persona, tipo, desde, hasta, n) -> str:
    partes = ["Marco y Chiara" if persona == "Ambos" else persona]
    if tipo and tipo != TIPO_TODOS:
        partes.append(tipo)
    if desde or hasta:
        partes.append(f"{_fmt_fecha(desde) if desde else 'inicio'} – {_fmt_fecha(hasta) if hasta else 'hoy'}")
    else:
        partes.append("todo el histórico")
    partes.append(f"{n} gastos")
    return " · ".join(partes)


def _titulo(titulo: str, sub: str) -> dict:
    return dict(text=f"{titulo}<br><sup>{sub}</sup>", x=0.01, xanchor="left")


def _base(fig: go.Figure, alto: int = 430) -> go.Figure:
    """Estilo común: euros en español (coma decimal, punto de miles), fondo claro."""
    fig.update_layout(
        separators=",.", template="plotly_white", height=alto,
        margin=dict(t=90, b=60, l=60, r=30),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0),
    )
    return fig


def _empty_fig(msg="Sin datos para mostrar") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, xref="paper", yref="paper",
                       x=0.5, y=0.5, font=dict(size=15, color=GRIS_OSCURO))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _base(fig, 300)


def figura_inicial() -> go.Figure:
    """Marcador de posición hasta que se selecciona la pestaña y se leen los datos."""
    return _empty_fig("Los datos se cargan al abrir esta pestaña")


def _msg_vacio(persona, tipo) -> str:
    quien = "" if persona == "Ambos" else f" de {persona}"
    extra = f" de tipo «{tipo}»" if tipo and tipo != TIPO_TODOS else ""
    return (f"No hay gastos{quien}{extra} en este periodo.<br>"
            "Probá con otro periodo (por ejemplo «Todo») o quitá el filtro de tipo.")


def _nota(fig: go.Figure, texto: str, y: float = -0.32) -> None:
    fig.add_annotation(text=texto, showarrow=False, xref="paper", yref="paper",
                       x=0, y=y, xanchor="left", font=dict(size=11, color=GRIS_OSCURO))


# --------------------------------------------------------------------------
# Tarjetas de métricas
# --------------------------------------------------------------------------

def tarjetas_resumen(rows, persona="Ambos", tipo=None, desde=None, hasta=None, hoy=None) -> str:
    """Números clave del periodo en una tabla Markdown corta."""
    hoy = hoy or date.today()
    desde, hasta = _parse_date(desde), _parse_date(hasta)
    rango = _vista(rows, tipo, desde, hasta)
    vista = _de_persona(rango, persona)
    if vista.is_empty():
        return "**Sin gastos para este filtro.** Probá con otro periodo o tipo de gasto."

    n = vista.height
    mediana = round(float(vista["monto"].median()), 2)
    cabecera = ["Total", "Nº de gastos", "Gasto mediano"]
    valores = [eur(_suma(vista)), str(n), eur(mediana)]
    pie = ""
    if persona == "Ambos":
        for p in PERSONAS:
            cabecera.append(f"Registrado por {p}")
            valores.append(eur(_suma(rango.filter(pl.col("persona") == p))))
    else:
        otra = next(p for p in PERSONAS if p != persona)
        cabecera.append(f"Registrado por {otra} (referencia)")
        valores.append(eur(_suma(rango.filter(pl.col("persona") == otra))))
        pie = f"\n\n*La última tarjeta ignora el filtro de Persona: es lo registrado por {otra} en el mismo periodo.*"
    tabla = ("| " + " | ".join(cabecera) + " |\n|" + "---|" * len(cabecera) +
             "\n| " + " | ".join(valores) + " |")
    return tabla + pie + f"\n\n*{NOTA_REGISTRADO}*"


# --------------------------------------------------------------------------
# Sub-tab General
# --------------------------------------------------------------------------

def gastos_en_tiempo(rows, persona="Ambos", tipo=None, desde=None, hasta=None, hoy=None) -> go.Figure:
    """Barras mensuales apiladas. Ambos: persona x tipo de gasto; una persona: sus tipos."""
    hoy = hoy or date.today()
    desde, hasta = _parse_date(desde), _parse_date(hasta)
    rango = _vista(rows, tipo, desde, hasta)
    vista = _de_persona(rango, persona)
    if vista.is_empty():
        return _empty_fig(_msg_vacio(persona, tipo))

    primero = rango["fecha"].min().replace(day=1)
    ultimo = rango["fecha"].max().replace(day=1)
    meses = _meses_entre(primero, ultimo)
    estados = [_estado_mes(m, hoy, desde, hasta) for m in meses]
    etiquetas = [_etq_mes(m) + _SUFIJO_ESTADO[e] for m, e in zip(meses, estados)]
    opacidad = [1 if e == "Completo" else OPACIDAD_NO_COMPLETO for e in estados]

    mensual = (
        vista.with_columns(pl.col("fecha").dt.truncate("1mo").alias("mes"))
        .group_by(["mes", "persona", "tipo_de_gasto"]).agg(money(pl.col("monto").sum()).alias("total"))
    )
    mapa = {(r["mes"], r["persona"], r["tipo_de_gasto"]): r["total"] for r in mensual.iter_rows(named=True)}
    series = [k for k in COLOR_SERIE if any((m, *k) in mapa for m in meses)]

    fig = go.Figure()
    for p, t in series:
        ys = [mapa.get((m, p, t), 0.0) for m in meses]
        fig.add_trace(go.Bar(
            name=f"{p} · {t}" if persona == "Ambos" else t,
            x=etiquetas, y=ys,
            marker=dict(color=COLOR_SERIE[(p, t)], opacity=opacidad),
            customdata=[eur(v) for v in ys],
            hovertemplate="%{x}<br>" + f"{p} · {t}" + ": %{customdata}<extra></extra>",
        ))
    totales = [round(sum(mapa.get((m, p, t), 0.0) for p, t in series), 2) for m in meses]
    fig.add_trace(go.Scatter(
        x=etiquetas, y=totales, mode="text", text=[_eur0(v) for v in totales],
        textposition="top center", showlegend=False, hoverinfo="skip", cliponaxis=False,
    ))

    completos = [tot for m, e, tot in zip(meses, estados, totales) if e == "Completo"]
    quien = _quien(persona)
    if len(completos) >= MIN_MESES_TENDENCIA:
        prom = round(sum(completos) / len(completos), 2)
        fig.add_trace(go.Scatter(
            x=etiquetas, y=[prom] * len(etiquetas), mode="lines",
            line=dict(color=GRIS_OSCURO, dash="dash", width=2),
            name=f"Promedio de meses completos ({_eur0(prom)})",
            hovertemplate="Promedio: " + eur(prom) + "<extra></extra>",
        ))
        verbo = "registran" if persona == "Ambos" else "registra"
        titulo = f"{quien} {verbo} {_eur0(prom)} al mes en promedio ({len(completos)} meses completos)"
    else:
        verbo = "registraron" if persona == "Ambos" else "registró"
        titulo = f"{quien} {verbo} {_eur0(_suma(vista))} en el periodo"
        _nota(fig, "Menos de 3 meses completos: se muestran valores, sin promedio ni tendencia. "
                   "Las barras claras son meses en curso o parciales.")

    fig.update_layout(
        title=_titulo(titulo, _subtitulo(persona, tipo, desde, hasta, vista.height)),
        barmode="stack",
        xaxis_title="Mes", yaxis_title="Gasto mensual registrado (€)",
    )
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero",
                     range=[0, max(totales) * 1.15 if max(totales) > 0 else 1])
    return _base(fig)


def registrado_por_persona(rows, persona="Ambos", tipo=None, desde=None, hasta=None, hoy=None) -> go.Figure:
    """Cuánto registró cada persona, en euros (barras agrupadas Marco vs Chiara).

    Con 2 meses o más del rango: barras mensuales; con un solo mes: por tipo de gasto.
    Ignora el filtro de persona: con una persona la resalta y deja a la otra en gris,
    como referencia neutral en euros (no como parte de un total)."""
    hoy = hoy or date.today()
    desde, hasta = _parse_date(desde), _parse_date(hasta)
    rango = _vista(rows, tipo, desde, hasta)
    if rango.is_empty():
        return _empty_fig(_msg_vacio("Ambos", tipo))

    meses = _meses_entre(rango["fecha"].min().replace(day=1), rango["fecha"].max().replace(day=1))
    por_mes = len(meses) > 1
    if por_mes:
        estados = [_estado_mes(m, hoy, desde, hasta) for m in meses]
        cats = [_etq_mes(m) + _SUFIJO_ESTADO[e] for m, e in zip(meses, estados)]
        opacidad = [1 if e == "Completo" else OPACIDAD_NO_COMPLETO for e in estados]
        claves = meses
        agrupado = rango.with_columns(pl.col("fecha").dt.truncate("1mo").alias("k"))
    else:
        cats = [t for t in TIPO_GASTO_OPTIONS if not rango.filter(pl.col("tipo_de_gasto") == t).is_empty()]
        opacidad = 1
        claves = cats
        agrupado = rango.with_columns(pl.col("tipo_de_gasto").alias("k"))
    tot = agrupado.group_by(["k", "persona"]).agg(money(pl.col("monto").sum()).alias("total"))
    mapa = {(r["k"], r["persona"]): r["total"] for r in tot.iter_rows(named=True)}

    fig = go.Figure()
    for p in PERSONAS:
        ys = [mapa.get((k, p), 0.0) for k in claves]
        color = COLOR_PERSONA[p] if persona in ("Ambos", p) else GRIS
        etiquetas = [_eur0(v) for v in ys]
        if por_mes:
            fig.add_trace(go.Bar(
                name=f"Registrado por {p}", x=cats, y=ys, marker=dict(color=color, opacity=opacidad),
                text=etiquetas, textposition="outside", cliponaxis=False,
                customdata=[eur(v) for v in ys],
                hovertemplate="%{x}<br>" + p + ": %{customdata}<extra></extra>",
            ))
        else:
            fig.add_trace(go.Bar(
                name=f"Registrado por {p}", y=cats, x=ys, orientation="h", marker_color=color,
                text=etiquetas, textposition="outside", cliponaxis=False,
                customdata=[eur(v) for v in ys],
                hovertemplate="%{y}<br>" + p + ": %{customdata}<extra></extra>",
            ))
    a, b = PERSONAS
    ta = _suma(rango.filter(pl.col("persona") == a))
    tb = _suma(rango.filter(pl.col("persona") == b))
    cuando = (f"en {MESES_LARGO[meses[0].month - 1]}" if not por_mes and desde and desde.day == 1
              and hasta and (hasta.year, hasta.month) == (desde.year, desde.month) else "en el periodo")
    titulo = f"{a} registró {_eur0(ta)} y {b} {_eur0(tb)} {cuando}"
    maximo = max(max(mapa.values(), default=0.0), 1.0)
    if por_mes:
        fig.update_layout(barmode="group", xaxis_title="Mes", yaxis_title="Registrado (€)")
        fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", range=[0, maximo * 1.2])
        nota = "Barras claras: meses en curso o parciales. "
    else:
        fig.update_layout(barmode="group", xaxis_title="Registrado (€)", yaxis_title="")
        fig.update_xaxes(tickformat=",.0f", ticksuffix=" €", range=[0, maximo * 1.25])
        fig.update_yaxes(autorange="reversed")
        nota = ""
    fig.update_layout(title=_titulo(titulo, _subtitulo("Ambos", tipo, desde, hasta, rango.height)))
    _nota(fig, nota + ("Ignora el filtro de Persona: la otra persona va en gris como referencia. "
                       if persona != "Ambos" else "") + "Registrado no es aportado.")
    return _base(fig)


# --------------------------------------------------------------------------
# Sub-tab por categoría
# --------------------------------------------------------------------------

def gasto_por_categoria(rows, persona="Ambos", tipo=None, desde=None, hasta=None) -> go.Figure:
    """Barras horizontales por categoría, de mayor a menor (Ambos: apiladas por persona)."""
    desde, hasta = _parse_date(desde), _parse_date(hasta)
    rango = _vista(rows, tipo, desde, hasta)
    vista = _de_persona(rango, persona)
    if vista.is_empty():
        return _empty_fig(_msg_vacio(persona, tipo))

    por_cat = (vista.group_by("categoria").agg(money(pl.col("monto").sum()).alias("total"))
               .sort("total", descending=True))
    cats = por_cat["categoria"].to_list()
    totales = por_cat["total"].to_list()
    total = sum(totales)

    fig = go.Figure()
    personas = PERSONAS if persona == "Ambos" else [persona]
    for p in personas:
        sub = vista.filter(pl.col("persona") == p).group_by("categoria").agg(
            money(pl.col("monto").sum()).alias("total"))
        mp = dict(zip(sub["categoria"].to_list(), sub["total"].to_list()))
        xs = [mp.get(c, 0.0) for c in cats]
        fig.add_trace(go.Bar(
            name=p, y=cats, x=xs, orientation="h", marker_color=COLOR_PERSONA[p],
            customdata=[eur(v) for v in xs],
            hovertemplate="%{y}<br>" + p + ": %{customdata}<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=totales, y=cats, mode="text", text=[_eur0(v) for v in totales],
        textposition="middle right", showlegend=False, hoverinfo="skip", cliponaxis=False,
    ))

    de = "de Marco y Chiara" if persona == "Ambos" else f"de {persona}"
    if len(cats) == 1 or total <= 0:
        titulo = f"{cats[0]} es todo el gasto {de}"
    else:
        top = cats[:2]
        titulo = f"{top[0]} y {top[1]} concentran el {pct(sum(totales[:2]) / total * 100)} del gasto {de}"
    fig.update_layout(
        title=_titulo(titulo, _subtitulo(persona, tipo, desde, hasta, vista.height)),
        barmode="stack", xaxis_title="Gasto (€)", yaxis_title="",
        showlegend=persona == "Ambos",
    )
    fig.update_xaxes(tickformat=",.0f", ticksuffix=" €", range=[0, max(totales) * 1.2])
    fig.update_yaxes(autorange="reversed")
    return _base(fig, max(330, 60 + 36 * len(cats)))


def mezcla_categorias(rows, persona="Ambos", tipo=None, desde=None, hasta=None) -> go.Figure:
    """Barras agrupadas: qué % de lo registrado por cada persona va a cada categoría.

    Ignora a propósito el filtro de persona (compara a las dos)."""
    desde, hasta = _parse_date(desde), _parse_date(hasta)
    rango = _vista(rows, tipo, desde, hasta)
    if rango.is_empty():
        return _empty_fig(_msg_vacio("Ambos", tipo))
    tot = {p: _suma(rango.filter(pl.col("persona") == p)) for p in PERSONAS}
    faltan = [p for p in PERSONAS if tot[p] <= 0]
    if faltan:
        return _empty_fig(f"{' y '.join(faltan)} no tiene gastos en este periodo:<br>"
                          "no se puede comparar la mezcla de categorías.")

    por = (rango.group_by(["categoria", "persona"]).agg(money(pl.col("monto").sum()).alias("total")))
    mapa = {(r["categoria"], r["persona"]): r["total"] for r in por.iter_rows(named=True)}
    cats = sorted({c for c, _ in mapa}, key=lambda c: -sum(mapa.get((c, p), 0.0) / tot[p] for p in PERSONAS))
    share = {(c, p): mapa.get((c, p), 0.0) / tot[p] * 100 for c in cats for p in PERSONAS}

    fig = go.Figure()
    for p in PERSONAS:
        color = COLOR_PERSONA[p] if persona in ("Ambos", p) else GRIS
        fig.add_trace(go.Bar(
            name=p, y=cats, x=[share[(c, p)] for c in cats], orientation="h", marker_color=color,
            text=[pct(share[(c, p)]) for c in cats], textposition="outside",
            customdata=[eur(mapa.get((c, p), 0.0)) for c in cats],
            hovertemplate="%{y}<br>" + p + ": %{x:,.1f} % de lo registrado (%{customdata})<extra></extra>",
        ))
    dif = max(cats, key=lambda c: abs(share[(c, PERSONAS[0])] - share[(c, PERSONAS[1])]))
    a, b = PERSONAS
    titulo = (f"{dif} marca la mayor diferencia: {pct(share[(dif, a)])} de lo registrado por {a} "
              f"vs {pct(share[(dif, b)])} de lo de {b}")
    n = rango.height
    fig.update_layout(
        title=_titulo(titulo, f"Mezcla de categorías · {a} vs {b} · {n} gastos"),
        barmode="group", xaxis_title="Parte de lo registrado por cada persona (%)", yaxis_title="",
    )
    fig.update_xaxes(range=[0, max(share.values()) * 1.2], ticksuffix=" %", tickformat=",.0f")
    fig.update_yaxes(autorange="reversed")
    if persona != "Ambos":
        otra = next(p for p in PERSONAS if p != persona)
        _nota(fig, f"Este gráfico ignora el filtro de Persona a propósito: compara a ambos. "
                   f"{otra} va en gris.", y=-0.2)
    return _base(fig, max(380, 90 + 46 * len(cats)))


def aviso_categorias(rows, persona="Ambos", tipo=None, desde=None, hasta=None) -> str:
    """Aviso Markdown si hay gastos en «Otros» o sin categoría (columna de texto `categoria`)."""
    desde, hasta = _parse_date(desde), _parse_date(hasta)
    rango = _vista(rows, tipo, desde, hasta)
    vista = _de_persona(rango, persona)
    if vista.is_empty():
        return ""
    dudosos = vista.filter(pl.col("categoria").is_in(CATEGORIAS_DUDOSAS))
    if dudosos.is_empty():
        return ""
    n_otros = dudosos.filter(pl.col("categoria") == "Otros").height
    n_sin = dudosos.height - n_otros
    detalle = []
    if n_otros:
        detalle.append(f"{n_otros} en «Otros»")
    if n_sin:
        detalle.append(f"{n_sin} sin categoría")
    total = _suma(vista)
    proporcion = _suma(dudosos) / total * 100 if total > 0 else 0.0
    return (f"**Aviso:** {dudosos.height} de {vista.height} gastos ({' y '.join(detalle)}) suman "
            f"{eur(_suma(dudosos))}, el {pct(proporcion)} del total. Las categorías de estos gráficos "
            "son menos precisas hasta reclasificarlos.")
