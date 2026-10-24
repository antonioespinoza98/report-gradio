"""Métricas de gasto por periodo: agregación, estadística descriptiva, tarjetas y gráfico."""
from datetime import date
from html import escape
from statistics import median

import plotly.graph_objects as go
import polars as pl

from utils.money import money

# eur/pct deben vivir en utils/money.py (pendiente de data-engineer). Mientras no
# existan allí, se usan las copias de transforms/viajes_analisis.py.
try:
    from utils.money import eur, pct
except ImportError:  # pragma: no cover
    from transforms.viajes_analisis import eur, pct

# Etiqueta del grano -> intervalo de truncado de Polars. Las semanas empiezan el lunes.
GRANOS = {
    "Diario": "1d",
    "Semanal": "1w",
    "Mensual": "1mo",
    "Anual": "1y",
}

AZUL = "#1f77b4"
GRIS = "#b8bec6"
NARANJA = "#d95f02"

MIN_COMPLETOS = 3      # con menos periodos completos no se resumen promedios
MIN_GASTOS_ATIPICOS = 8  # con menos gastos los cuartiles son inestables
DIF_MEDIA_MEDIANA = 0.20
MAX_ETIQUETAS_BARRAS = 20
MAX_ATIPICOS_TABLA = 15

_PERIODOS_COLS = {
    "Periodo": [], "Total": [], "Nº gastos": [], "Ticket promedio": [],
    "Variación": [], "Estado": [],
}
_ATIPICOS_COLS = {"Fecha": [], "Descripción": [], "Persona": [], "Monto": []}


# --------------------------------------------------------------------------
# Formato
# --------------------------------------------------------------------------

def _eur0(v) -> str:
    """Euros sin decimales cuando son exactos (para etiquetas compactas)."""
    return eur(v).replace(",00 €", " €")


def _fecha(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _eur_signo(v) -> str:
    if v is None:
        return "—"
    return ("+" if v > 0 else "") + eur(v)


def _pct_signo(frac) -> str:
    """Variación relativa (fracción) con signo y coma decimal: +12,3 %."""
    if frac is None:
        return "—"
    return ("+" if frac > 0 else "") + pct(frac * 100)


def _variacion_txt(var_abs, frac) -> str:
    if var_abs is None or frac is None:
        return "—"
    return f"{_eur_signo(var_abs)} ({_pct_signo(frac)})"


# --------------------------------------------------------------------------
# Filtros y agregación
# --------------------------------------------------------------------------

def filtrar_tipo(rows: list[dict], tipo: str | None) -> list[dict]:
    """Filtra por tipo de gasto en Python (models/ no lo soporta)."""
    if not tipo:
        return rows
    return [r for r in rows if r.get("tipo_de_gasto") == tipo]


def _fin(inicio: pl.Expr, every: str) -> pl.Expr:
    """Último día calendario que cubre un periodo que empieza en `inicio`."""
    if every == "1d":
        return inicio
    if every == "1w":
        return inicio.dt.offset_by("6d")
    return inicio.dt.offset_by(every).dt.offset_by("-1d")


def _etiqueta(grano: str) -> pl.Expr:
    """Etiqueta legible de cada periodo."""
    if grano == "Diario":
        return pl.col("inicio").dt.strftime("%Y-%m-%d")
    if grano == "Semanal":
        return pl.concat_str([
            pl.col("inicio").dt.strftime("%Y-%m-%d"),
            pl.lit(" → "),
            pl.col("fin").dt.strftime("%Y-%m-%d"),
        ])
    if grano == "Mensual":
        return pl.col("inicio").dt.strftime("%Y-%m")
    return pl.col("inicio").dt.strftime("%Y")


def por_periodo(rows: list[dict], grano: str, hoy: date | None = None) -> pl.DataFrame:
    """
    Agrega los gastos en periodos del grano indicado.

    Columnas: inicio, fin, periodo, total, n, ticket, estado, completo,
    var_abs, variacion.

    - Un periodo es `Completo` cuando su último día ya pasó; el que contiene
      hoy es `En curso` y los posteriores `Futuro`. Ambos quedan fuera de las
      estadísticas.
    - Los periodos sin gastos entre el primero y hoy se rellenan con total 0
      (un mes sin gastos es un mes de gasto 0, no un dato ausente).
    - `var_abs` / `variacion` (fracción) comparan un periodo Completo con el
      periodo inmediatamente anterior; `variacion` es None si el anterior es 0.
      El periodo en curso NO se compara: se excluye (no es comparable con uno
      terminado).
    """
    hoy = hoy or date.today()
    every = GRANOS[grano]

    if not rows:
        return pl.DataFrame(_PERIODOS_COLS)

    df = pl.DataFrame(rows).select(["fecha", "monto"])

    agg = (
        df.with_columns(pl.col("fecha").dt.truncate(every).alias("inicio"))
        .group_by("inicio")
        .agg(
            money(pl.col("monto").sum()).alias("total"),
            pl.len().alias("n"),
            money(pl.col("monto").mean()).alias("ticket"),
        )
        .sort("inicio")
    )

    # Relleno de periodos vacíos hasta el periodo que contiene hoy.
    hoy_inicio = pl.select(pl.lit(hoy).dt.truncate(every)).item()
    primero = agg["inicio"].min()
    tope = min(agg["inicio"].max(), hoy_inicio)
    if primero <= tope:
        calendario = pl.DataFrame(
            {"inicio": pl.date_range(primero, tope, interval=every, eager=True)}
        )
        agg = (
            calendario.join(agg, on="inicio", how="full", coalesce=True)
            .with_columns(
                pl.col("total").fill_null(0.0),
                pl.col("n").fill_null(0),
            )
            .sort("inicio")
        )

    base = (
        agg.with_columns(_fin(pl.col("inicio"), every).alias("fin"))
        .with_columns(
            pl.when(pl.col("fin") < hoy).then(pl.lit("Completo"))
            .when(pl.col("inicio") > hoy).then(pl.lit("Futuro"))
            .otherwise(pl.lit("En curso"))
            .alias("estado")
        )
        .with_columns((pl.col("estado") == "Completo").alias("completo"))
        .with_columns(_etiqueta(grano).alias("periodo"))
    )

    prev = pl.col("total").shift(1)
    var_abs = pl.when(pl.col("completo") & prev.is_not_null()).then(
        money(pl.col("total") - prev)
    )
    base = base.with_columns(var_abs.alias("var_abs"))
    return base.with_columns(
        pl.when(pl.col("var_abs").is_not_null() & (prev > 0))
        .then((pl.col("var_abs") / prev).round(4))
        .alias("variacion")
    )


def a_tabla(per: pl.DataFrame) -> pl.DataFrame:
    """Tabla de detalle por periodo para mostrar (euros en formato español)."""
    if per.is_empty():
        return pl.DataFrame(_PERIODOS_COLS)
    filas = per.to_dicts()
    return pl.DataFrame({
        "Periodo": [f["periodo"] for f in filas],
        "Total": [eur(f["total"]) for f in filas],
        "Nº gastos": [f["n"] for f in filas],
        "Ticket promedio": [eur(f["ticket"]) for f in filas],
        "Variación": [_variacion_txt(f["var_abs"], f["variacion"]) for f in filas],
        "Estado": [f["estado"] for f in filas],
    })


# --------------------------------------------------------------------------
# Estadística descriptiva
# --------------------------------------------------------------------------

def _completos(per: pl.DataFrame) -> pl.DataFrame:
    return per.filter(pl.col("estado") == "Completo") if not per.is_empty() else per


def _tipico(valores: pl.Series) -> tuple[float, str, float, float]:
    """
    Valor típico: la media, salvo que difiera más de 20 % de la mediana
    (señal de asimetría), en cuyo caso se prefiere la mediana.
    Devuelve (valor, nombre de la medida usada, media, mediana).
    """
    media = round(float(valores.mean()), 2)
    mediana = round(float(valores.median()), 2)
    ref = abs(mediana)
    if ref > 0 and abs(media - mediana) / ref > DIF_MEDIA_MEDIANA:
        return mediana, "mediana", media, mediana
    return media, "media", media, mediana


def atipicos(rows: list[dict]) -> pl.DataFrame:
    """Gastos fuera de [p25 − 1,5·IQR, p75 + 1,5·IQR], con fecha y descripción."""
    if len(rows) < MIN_GASTOS_ATIPICOS:
        return pl.DataFrame(_ATIPICOS_COLS)
    df = pl.DataFrame(rows).select(["fecha", "descripcion", "persona", "monto"])
    q1 = df["monto"].quantile(0.25, interpolation="linear")
    q3 = df["monto"].quantile(0.75, interpolation="linear")
    iqr = q3 - q1
    bajo, alto = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    fuera = df.filter((pl.col("monto") < bajo) | (pl.col("monto") > alto)).sort(
        "monto", descending=True
    )
    if fuera.is_empty():
        return pl.DataFrame(_ATIPICOS_COLS)
    filas = fuera.to_dicts()
    return pl.DataFrame({
        "Fecha": [_fecha(f["fecha"]) for f in filas],
        "Descripción": [f["descripcion"] for f in filas],
        "Persona": [f["persona"] for f in filas],
        "Monto": [eur(f["monto"]) for f in filas],
    })


def _extremo(per: pl.DataFrame, mayor: bool) -> str:
    if per.is_empty():
        return "—"
    fila = per.sort("total", descending=mayor).row(0, named=True)
    return f"{fila['periodo']} · {eur(fila['total'])}"


def _gasto_extremo(rows: list[dict], mayor: bool) -> str:
    if not rows:
        return "—"
    fila = sorted(rows, key=lambda r: float(r["monto"]), reverse=mayor)[0]
    return f"{fila['descripcion']} ({_fecha(fila['fecha'])}) · {eur(fila['monto'])}"


def _futuros(futuros: pl.DataFrame) -> str:
    if futuros.is_empty():
        return "—"
    return f"{int(futuros['n'].sum())} gasto(s) · {eur(futuros['total'].sum())}"


def resumen(rows: list[dict], grano: str, hoy: date | None = None,
            per: pl.DataFrame | None = None) -> pl.DataFrame:
    """
    Estadísticas por periodo (promedio, mediana, extremos) con su n.

    Solo usa periodos completos. Con menos de 3 se indica "datos insuficientes"
    en vez de promedios poco fiables. Pasá `per` para no recalcular la agregación.
    """
    if per is None:
        per = por_periodo(rows, grano, hoy or date.today())
    comp = _completos(per)
    n = comp.height
    fut = per.filter(pl.col("estado") == "Futuro") if not per.is_empty() else per
    cur = per.filter(pl.col("estado") == "En curso") if not per.is_empty() else per
    insuf = f"Datos insuficientes ({n} periodos completos; mínimo {MIN_COMPLETOS})"

    if n >= MIN_COMPLETOS:
        valor, usada, media, mediana = _tipico(comp["total"])
        tipico = (f"{eur(valor)} ({usada}; media {eur(media)}, mediana {eur(mediana)})"
                  if usada == "mediana" else f"{eur(valor)} (media)")
        promedio, mediana_txt = eur(media), eur(mediana)
        tipico_txt = f"{tipico} · n = {n}"
        promedio_txt = f"{promedio} · n = {n}"
        mediana_txt = f"{mediana_txt} · n = {n}"
    else:
        tipico_txt = promedio_txt = mediana_txt = insuf

    # Ticket (gasto individual): misma regla media/mediana, n = nº de gastos.
    if len(rows) >= MIN_COMPLETOS:
        montos = pl.Series([float(r["monto"]) for r in rows])
        v, usada, media, mediana = _tipico(montos)
        ticket_txt = (f"{eur(v)} ({usada}; media {eur(media)}) · n = {len(rows)}"
                      if usada == "mediana" else f"{eur(v)} (media) · n = {len(rows)}")
    else:
        ticket_txt = f"Datos insuficientes ({len(rows)} gastos)"

    n_atip = atipicos(rows).height
    if len(rows) < MIN_GASTOS_ATIPICOS:
        atip_txt = f"Datos insuficientes ({len(rows)} gastos; mínimo {MIN_GASTOS_ATIPICOS})"
    else:
        atip_txt = f"{n_atip} de {len(rows)} (tabla: los {MAX_ATIPICOS_TABLA} mayores)"

    ext_n = f" · n = {n}" if n else ""
    filas = [
        (f"Periodos completos ({grano.lower()})", str(n)),
        ("Gasto típico por periodo", tipico_txt),
        ("Promedio por periodo", promedio_txt),
        ("Mediana por periodo", mediana_txt),
        ("Periodo más caro", _extremo(comp, True) + (ext_n if n else "")),
        ("Periodo más barato", _extremo(comp, False) + (ext_n if n else "")),
        ("Gasto típico por compra", ticket_txt),
        ("Gasto individual más grande", _gasto_extremo(rows, True)),
        ("Gasto individual más pequeño", _gasto_extremo(rows, False)),
        ("Gastos atípicos (1,5·IQR)", atip_txt),
        ("Periodo en curso (excluido)", _extremo(cur, True)),
        ("Gastos con fecha futura (excluidos)", _futuros(fut)),
    ]
    return pl.DataFrame({"Métrica": [a for a, _ in filas], "Valor": [b for _, b in filas]})


# --------------------------------------------------------------------------
# Tarjetas
# --------------------------------------------------------------------------

_CARD_STYLE = (
    "flex:1;min-width:190px;padding:14px 16px;border-radius:10px;"
    "border:1px solid var(--border-color-primary);"
    "background:var(--block-background-fill);"
)


def _tarjeta(titulo: str, valor: str, detalle: str = "") -> str:
    return (
        f'<div style="{_CARD_STYLE}">'
        f'<div style="font-size:0.85em;opacity:0.75">{escape(titulo)}</div>'
        f'<div style="font-size:1.6em;font-weight:700;margin:4px 0">{escape(valor)}</div>'
        f'<div style="font-size:0.85em;opacity:0.75">{escape(detalle)}</div>'
        "</div>"
    )


def _ultimos(per: pl.DataFrame):
    """(último periodo completo, el anterior) como dicts, o None."""
    comp = _completos(per)
    if comp.is_empty():
        return None, None
    ultimo = comp.row(comp.height - 1, named=True)
    idx = per.height - 1 - per.reverse()["periodo"].to_list().index(ultimo["periodo"])
    previo = per.row(idx - 1, named=True) if idx > 0 else None
    return ultimo, previo


def tarjetas(rows: list[dict], per: pl.DataFrame, grano: str) -> str:
    """HTML con cuatro tarjetas: total, nº de gastos, último periodo completo, variación."""
    total = round(sum(float(r["monto"]) for r in rows), 2)
    n = len(rows)
    ultimo, previo = _ultimos(per)

    if n == 0:
        t1 = _tarjeta("Total del rango", "—", "Sin gastos en el rango")
        t2 = _tarjeta("Nº de gastos", "0", "")
    else:
        t1 = _tarjeta("Total del rango", eur(total), "No depende de «Agrupar por»")
        t2 = _tarjeta("Nº de gastos", str(n), f"Gasto típico (mediana) {eur(median(float(r['monto']) for r in rows))}")

    if ultimo is None:
        t3 = _tarjeta(f"Último periodo completo ({grano.lower()})", "—", "Aún no hay periodos completos")
        t4 = _tarjeta("Variación vs anterior", "—", "Sin periodo completo")
    else:
        t3 = _tarjeta(f"Último periodo completo ({grano.lower()})", eur(ultimo["total"]),
                      f"{ultimo['periodo']} · {ultimo['n']} gastos")
        if ultimo["variacion"] is None or previo is None:
            motivo = ("Sin periodo anterior" if previo is None
                      else f"El anterior ({previo['periodo']}) fue 0 €")
            t4 = _tarjeta("Variación vs anterior", "—", motivo)
        else:
            flecha = "▲" if ultimo["var_abs"] > 0 else ("▼" if ultimo["var_abs"] < 0 else "■")
            t4 = _tarjeta("Variación vs anterior",
                          f"{flecha} {_pct_signo(ultimo['variacion'])}",
                          f"{_eur_signo(ultimo['var_abs'])} vs {previo['periodo']} ({eur(previo['total'])})")
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:12px">'
        + t1 + t2 + t3 + t4 + "</div>"
    )


# --------------------------------------------------------------------------
# Gráfico
# --------------------------------------------------------------------------

def _fig_vacia(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, xref="paper", yref="paper",
                       x=0.5, y=0.5, font=dict(size=16))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=300)
    return fig


def _titulo(per: pl.DataFrame, grano: str, mediana: float | None) -> str:
    """Título con la conclusión, generado desde los datos."""
    comp = _completos(per)
    if comp.height < MIN_COMPLETOS:
        return f"Datos insuficientes: solo {comp.height} periodos completos ({grano.lower()})"
    ultimo, previo = _ultimos(per)
    if grano == "Diario":
        return (f"Gasto diario típico: {_eur0(mediana)}; el último día completo "
                f"({ultimo['periodo']}) fue {_eur0(ultimo['total'])}")
    if ultimo["variacion"] is None or previo is None:
        return f"{ultimo['periodo']}: {_eur0(ultimo['total'])}, sin base de comparación"
    verbo = "subió" if ultimo["var_abs"] > 0 else ("bajó" if ultimo["var_abs"] < 0 else "se mantuvo")
    if verbo == "se mantuvo":
        return f"El gasto se mantuvo en {_eur0(ultimo['total'])} en {ultimo['periodo']}"
    return (f"El gasto {verbo} {pct(abs(ultimo['variacion']) * 100)} en {ultimo['periodo']}: "
            f"{_eur0(ultimo['total'])} (mediana {_eur0(mediana)})")


def _estilo(fig: go.Figure, titulo: str, max_y: float) -> go.Figure:
    fig.update_layout(
        title=titulo, separators=",.", height=420, plot_bgcolor="white",
        showlegend=False, hovermode="x unified",
        margin=dict(l=60, r=40, t=70, b=70),
    )
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero",
                     range=[0, max(max_y, 1) * 1.18], gridcolor="#eceff1",
                     title="Gasto por periodo (€)")
    fig.update_xaxes(type="category", tickangle=-45, title=None)
    return fig


def grafico(per: pl.DataFrame, grano: str) -> go.Figure:
    """
    Barras por periodo con mediana de periodos completos y "En curso" aparte.
    En grano Diario se dibuja la media móvil de 7 días (173 barras no se leen).
    """
    if per.is_empty():
        return _fig_vacia("Sin datos disponibles")

    comp = _completos(per)
    mediana = None
    if comp.height >= MIN_COMPLETOS:
        mediana = round(float(comp["total"].median()), 2)
    titulo = _titulo(per, grano, mediana)

    if grano == "Diario":
        return _grafico_diario(per, comp, mediana, titulo)

    periodos = per["periodo"].to_list()
    totales = per["total"].to_list()
    estados = per["estado"].to_list()
    colores = [AZUL if e == "Completo" else GRIS for e in estados]
    etiquetas = (
        [_eur0(t) + ("" if e == "Completo" else f"<br>{e}") for t, e in zip(totales, estados)]
        if len(periodos) <= MAX_ETIQUETAS_BARRAS
        else [("" if e == "Completo" else e) for e in estados]
    )

    fig = go.Figure(go.Bar(
        x=periodos, y=totales, marker_color=colores,
        marker_line=dict(color=[AZUL if e != "Completo" else "rgba(0,0,0,0)" for e in estados],
                         width=1.5),
        text=etiquetas, textposition="outside", cliponaxis=False,
        customdata=[[e, n] for e, n in zip(estados, per["n"].to_list())],
        hovertemplate="%{x}<br>%{y:,.2f} €<br>%{customdata[1]} gastos · %{customdata[0]}<extra></extra>",
    ))
    if mediana is not None:
        fig.add_hline(y=mediana, line_dash="dash", line_color=NARANJA,
                      annotation_text=f"Mediana (completos, n = {comp.height}): {_eur0(mediana)}",
                      annotation_position="top left", annotation_font_color=NARANJA)
    return _estilo(fig, titulo, max(totales))


def _grafico_diario(per, comp, mediana, titulo) -> go.Figure:
    if comp.height < 7:
        return _fig_vacia("Datos insuficientes para la media móvil de 7 días "
                          f"({comp.height} días completos)")
    ma = comp.with_columns(
        money(pl.col("total").rolling_mean(window_size=7, min_samples=7)).alias("ma")
    ).filter(pl.col("ma").is_not_null())
    fig = go.Figure(go.Scatter(
        x=ma["periodo"].to_list(), y=ma["ma"].to_list(), mode="lines",
        line=dict(color=AZUL, width=2.5), name="Media móvil 7 días",
        hovertemplate="%{x}<br>Media móvil 7 días: %{y:,.2f} €<extra></extra>",
    ))
    cur = per.filter(pl.col("estado") == "En curso")
    if not cur.is_empty():
        fila = cur.row(0, named=True)
        fig.add_trace(go.Scatter(
            x=[fila["periodo"]], y=[fila["total"]], mode="markers+text",
            marker=dict(color=GRIS, size=10, line=dict(color=AZUL, width=1.5)),
            text=[f"En curso: {_eur0(fila['total'])}"], textposition="top center",
            hovertemplate="%{x}<br>%{y:,.2f} € (en curso)<extra></extra>",
        ))
    if mediana is not None:
        fig.add_hline(y=mediana, line_dash="dash", line_color=NARANJA,
                      annotation_text=f"Mediana diaria (n = {comp.height}): {_eur0(mediana)}",
                      annotation_position="top left", annotation_font_color=NARANJA)
    fig.update_layout(title=titulo)
    top = max(ma["ma"].max(), mediana or 0, cur["total"].max() if not cur.is_empty() else 0)
    _estilo(fig, titulo, float(top))
    fig.update_yaxes(title="Media móvil de 7 días (€/día)")
    fig.update_xaxes(type="category", nticks=12, tickangle=-45)
    return fig


# --------------------------------------------------------------------------
# Punto de entrada para la UI
# --------------------------------------------------------------------------

def construir(rows: list[dict], grano: str, tipo: str | None = None, hoy: date | None = None):
    """
    Calcula todo con una sola agregación por periodo.

    Devuelve (tarjetas_html, resumen_df, atipicos_df, detalle_df, figura).
    """
    hoy = hoy or date.today()
    rows = filtrar_tipo(rows, tipo)
    per = por_periodo(rows, grano, hoy)
    return (
        tarjetas(rows, per, grano),
        resumen(rows, grano, hoy, per=per),
        atipicos(rows).head(MAX_ATIPICOS_TABLA),
        a_tabla(per),
        grafico(per, grano),
    )
