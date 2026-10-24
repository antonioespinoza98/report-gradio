"""Análisis de gastos por viaje: métricas, tablas y gráficos (Polars + Plotly)."""
from datetime import date

import plotly.graph_objects as go
import polars as pl

from utils.money import eur, money, pct

AZUL = "#1f77b4"
GRIS = "#b8bec6"
SIN_VIAJES = "Todavía no hay gastos asignados a un viaje."


def _fecha(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _fig_vacia(msg: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=16))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=300)
    return fig


def _layout(fig: go.Figure, title: str, height=380) -> go.Figure:
    fig.update_layout(
        title=title, separators=",.", height=height,
        plot_bgcolor="white", showlegend=False,
        margin=dict(l=40, r=40, t=60, b=40),
    )
    return fig


def opciones_viajes(viajes_rows: list[dict], gastos_rows: list[dict]) -> list[tuple[str, int]]:
    """Opciones del selector: solo viajes que tienen al menos un gasto."""
    con_gasto = {r["viaje_id"] for r in gastos_rows if r.get("viaje_id")}
    return [
        (f"{v['nombre']} · {_fecha(v['fecha_inicio'])} → {_fecha(v['fecha_fin'])}", v["id"])
        for v in viajes_rows if v["id"] in con_gasto
    ]


def _dias(inicio: date, fin: date, hoy: date) -> tuple[int, bool]:
    """Días transcurridos del viaje (inclusive) y si sigue en curso."""
    en_curso = inicio <= hoy <= fin
    tope = min(fin, hoy)
    return max((tope - inicio).days + 1, 1), en_curso


def _gastos_df(gastos_rows: list[dict], viaje_id: int | None = None) -> pl.DataFrame:
    df = pl.DataFrame(gastos_rows) if gastos_rows else pl.DataFrame()
    if df.is_empty() or "viaje_id" not in df.columns:
        return pl.DataFrame()
    df = df.filter(pl.col("viaje_id").is_not_null())
    if viaje_id is not None:
        df = df.filter(pl.col("viaje_id") == viaje_id)
    return df


def _viaje(viajes_rows, viaje_id):
    return next((v for v in viajes_rows if v["id"] == viaje_id), None)


def tabla_gastos(gastos_rows: list[dict], viaje_id: int) -> pl.DataFrame:
    """Gastos del viaje, ordenados por fecha."""
    df = _gastos_df(gastos_rows, viaje_id)
    if df.is_empty():
        return pl.DataFrame({"Fecha": [], "Persona": [], "Descripción": [],
                             "Categoría": [], "Tipo": [], "Monto": []})
    return df.sort(["fecha", "id"]).select(
        pl.col("fecha").dt.strftime("%d/%m/%Y").alias("Fecha"),
        pl.col("persona").alias("Persona"),
        pl.col("descripcion").alias("Descripción"),
        pl.col("categoria").alias("Categoría"),
        pl.col("tipo_de_gasto").alias("Tipo"),
        money(pl.col("monto")).alias("Monto"),
    )


def metricas_viaje(gastos_rows, viajes_rows, viaje_id, hoy: date | None = None) -> tuple[str, pl.DataFrame]:
    """Titular (Markdown) y tabla corta de métricas clave del viaje."""
    hoy = hoy or date.today()
    v = _viaje(viajes_rows, viaje_id)
    df = _gastos_df(gastos_rows, viaje_id)
    if v is None or df.is_empty():
        return SIN_VIAJES, pl.DataFrame({"Métrica": [], "Valor": []})

    n = df.height
    total = round(float(df["monto"].sum()), 2)
    dias, en_curso = _dias(v["fecha_inicio"], v["fecha_fin"], hoy)
    por_dia = round(total / dias, 2)
    media = round(float(df["monto"].mean()), 2)
    mediana = round(float(df["monto"].median()), 2)
    mayor = df.sort("monto", descending=True).row(0, named=True)
    diario = df.group_by("fecha").agg(pl.col("monto").sum().alias("t")).sort("t", descending=True)
    dia_caro = diario.row(0, named=True)
    cat = df.group_by("categoria").agg(pl.col("monto").sum().alias("t")).sort("t", descending=True)
    cat_top = cat.row(0, named=True)

    estado = " (en curso)" if en_curso else ""
    titulo = (f"### {v['nombre']}: {eur(total)} en {dias} días{estado}, "
              f"unos {eur(por_dia)} por día\n"
              f"{pct(cat_top['t'] / total * 100)} del gasto es {cat_top['categoria']}. "
              f"Basado en {n} gastos.")

    filas = [
        ("Total del viaje", eur(total)),
        ("Días considerados" + (" (hasta hoy)" if en_curso else ""), str(dias)),
        ("Gasto promedio por día", eur(por_dia)),
        ("Gasto típico (mediana)", f"{eur(mediana)} (media {eur(media)})"),
        ("Gasto más grande", f"{eur(mayor['monto'])} · {mayor['descripcion']} ({_fecha(mayor['fecha'])})"),
        ("Día más caro", f"{eur(dia_caro['t'])} · {_fecha(dia_caro['fecha'])}"),
        ("Cantidad de gastos", str(n)),
    ]
    personas = df.group_by("persona").agg(pl.col("monto").sum().alias("t")).sort("t", descending=True)
    # Reparto por persona solo cuando aporta (ambos pagaron algo).
    if personas.height > 1:
        for r in personas.iter_rows(named=True):
            filas.append((f"Gastó {r['persona']}", f"{eur(r['t'])} ({pct(r['t'] / total * 100)})"))
    else:
        filas.append(("Pagó todo", personas["persona"][0]))
    return titulo, pl.DataFrame({"Métrica": [f[0] for f in filas], "Valor": [f[1] for f in filas]})


def fig_categorias(gastos_rows, viaje_id) -> go.Figure:
    """Barras horizontales: gasto por categoría con % del total."""
    df = _gastos_df(gastos_rows, viaje_id)
    if df.is_empty():
        return _fig_vacia(SIN_VIAJES)
    cat = (df.group_by("categoria").agg(pl.col("monto").sum().alias("t"))
           .sort("t", descending=False))
    total = cat["t"].sum()
    top = cat.tail(1).row(0, named=True)
    colores = [AZUL if c == top["categoria"] else GRIS for c in cat["categoria"]]
    textos = [f"{eur(t)} · {pct(t / total * 100)}" for t in cat["t"]]
    fig = go.Figure(go.Bar(
        x=cat["t"].round(2), y=cat["categoria"], orientation="h",
        marker_color=colores, text=textos, textposition="outside",
        hovertemplate="%{y}<br>%{x:,.2f} €<extra></extra>", cliponaxis=False,
    ))
    fig.update_xaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero", showgrid=False)
    fig.update_layout(margin=dict(r=140))
    return _layout(fig, f"{top['categoria']} es la mayor categoría: "
                        f"{pct(top['t'] / total * 100)} del viaje",
                   height=max(300, 60 + 40 * cat.height))


def fig_acumulado(gastos_rows, viajes_rows, viaje_id, hoy: date | None = None) -> go.Figure:
    """Línea del gasto acumulado por día, con barras del gasto diario."""
    hoy = hoy or date.today()
    v = _viaje(viajes_rows, viaje_id)
    df = _gastos_df(gastos_rows, viaje_id)
    if v is None or df.is_empty():
        return _fig_vacia(SIN_VIAJES)
    fin = min(v["fecha_fin"], max(hoy, df["fecha"].max()))
    dias = pl.DataFrame({"fecha": pl.date_range(v["fecha_inicio"], max(fin, df["fecha"].max()), "1d", eager=True)})
    diario = (dias.join(df.group_by("fecha").agg(pl.col("monto").sum().alias("t")), on="fecha", how="left")
              .with_columns(pl.col("t").fill_null(0.0))
              .sort("fecha")
              .with_columns(pl.col("t").cum_sum().alias("acum")))
    total = round(float(diario["acum"][-1]), 2)
    caro = diario.sort("t", descending=True).row(0, named=True)
    colores = [AZUL if f == caro["fecha"] else GRIS for f in diario["fecha"]]
    fig = go.Figure()
    fig.add_bar(x=diario["fecha"], y=diario["t"].round(2), marker_color=colores, name="Diario",
                hovertemplate="%{x|%d/%m/%Y}<br>Día: %{y:,.2f} €<extra></extra>")
    fig.add_scatter(x=diario["fecha"], y=diario["acum"].round(2), mode="lines+markers", name="Acumulado",
                    line=dict(color="#333"),
                    hovertemplate="%{x|%d/%m/%Y}<br>Acumulado: %{y:,.2f} €<extra></extra>")
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero")
    fig.update_xaxes(tickformat="%d/%m")
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.2))
    return _layout(fig, f"El día más caro fue el {_fecha(caro['fecha'])}: {eur(caro['t'])} "
                        f"de {eur(total)} acumulados")


def comparativa(gastos_rows, viajes_rows, hoy: date | None = None) -> tuple[pl.DataFrame, go.Figure]:
    """Tabla y gráfico comparando costo por día entre viajes."""
    hoy = hoy or date.today()
    df = _gastos_df(gastos_rows)
    vacia = pl.DataFrame({"Viaje": [], "Desde": [], "Hasta": [], "Días": [], "Gastos": [],
                          "Total": [], "Por día": [], "Mediana gasto": [], "Estado": []})
    if df.is_empty():
        return vacia, _fig_vacia(SIN_VIAJES)
    agg = df.group_by("viaje_id").agg(
        pl.col("monto").sum().alias("total"),
        pl.col("monto").median().alias("mediana"),
        pl.len().alias("n"),
    )
    filas = []
    for r in agg.iter_rows(named=True):
        v = _viaje(viajes_rows, r["viaje_id"])
        if v is None:
            continue
        dias, en_curso = _dias(v["fecha_inicio"], v["fecha_fin"], hoy)
        dias_viaje = (v["fecha_fin"] - v["fecha_inicio"]).days + 1
        dias_usar = dias if en_curso else dias_viaje
        filas.append({
            "Viaje": v["nombre"], "inicio": v["fecha_inicio"], "fin": v["fecha_fin"],
            "Días": dias_usar, "Gastos": r["n"], "total": round(r["total"], 2),
            "por_dia": round(r["total"] / dias_usar, 2), "mediana": round(r["mediana"], 2),
            "Estado": "En curso" if en_curso else "Completo",
        })
    if not filas:
        return vacia, _fig_vacia(SIN_VIAJES)
    c = pl.DataFrame(filas).sort("inicio", descending=True)
    tabla = c.select(
        "Viaje",
        pl.col("inicio").dt.strftime("%d/%m/%Y").alias("Desde"),
        pl.col("fin").dt.strftime("%d/%m/%Y").alias("Hasta"),
        "Días", "Gastos",
        pl.col("total").alias("Total"),
        pl.col("por_dia").alias("Por día"),
        pl.col("mediana").alias("Mediana gasto"),
        "Estado",
    )
    g = c.sort("por_dia")
    top = g.tail(1).row(0, named=True)
    colores = [AZUL if n == top["Viaje"] else GRIS for n in g["Viaje"]]
    etiquetas = [f"{n}{' (en curso)' if e == 'En curso' else ''}" for n, e in zip(g["Viaje"], g["Estado"])]
    fig = go.Figure(go.Bar(
        x=g["por_dia"], y=etiquetas, orientation="h", marker_color=colores,
        text=[f"{eur(p)}/día · total {eur(t)}" for p, t in zip(g["por_dia"], g["total"])],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:,.2f} € por día<extra></extra>",
    ))
    fig.update_xaxes(tickformat=",.0f", ticksuffix=" €", rangemode="tozero", showgrid=False)
    fig.update_layout(margin=dict(r=200))
    return tabla, _layout(fig, f"{top['Viaje']} es el viaje más caro por día: {eur(top['por_dia'])}",
                          height=max(260, 100 + 60 * g.height))
