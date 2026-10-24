import polars as pl
import plotly.graph_objects as go
from datetime import date as date_type
from utils.money import money

def _parse_date(d):
    """Convert a string 'YYYY-MM-DD' or date object to a date object."""
    if d is None:
        return None
    if isinstance(d, date_type):
        return d
    try:
        return date_type.fromisoformat(str(d))
    except Exception:
        return None

def _filter_dates(df: pl.DataFrame, date_from, date_to) -> pl.DataFrame:
    """Apply date range filter, converting strings to date objects as needed."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    if d_from:
        df = df.filter(pl.col("fecha") >= d_from)
    if d_to:
        df = df.filter(pl.col("fecha") <= d_to)
    return df

def _empty_fig(msg="Sin datos disponibles") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


def gastos_en_tiempo(rows: list[dict], date_from=None, date_to=None) -> go.Figure:
    """Line chart of spending over time (by month)."""
    if not rows:
        return _empty_fig()

    df = pl.DataFrame(rows)
    df = _filter_dates(df, date_from, date_to)

    if df.is_empty():
        return _empty_fig()

    df = df.with_columns(
        pl.col("fecha").dt.strftime("%Y-%m-%d").alias("day")
    )
    summary = df.group_by("day").agg(
        money(pl.col("monto").sum()).alias("total")
    ).sort("day")

    fig = go.Figure(data=[
        go.Scatter(x=summary["day"], y=summary["total"], mode="lines+markers", line_color="darkblue")
    ])
    fig.update_layout(
        title="Gastos en el Tiempo",
        xaxis_title="Fecha",
        yaxis_title="Monto Total",
        hovermode="x"
    )
    return fig


def comparativa_personas(rows: list[dict], date_from=None, date_to=None) -> go.Figure:
    """Side-by-side bar chart comparing Marco vs Chiara."""
    if not rows:
        return _empty_fig()

    df = pl.DataFrame(rows)
    df = _filter_dates(df, date_from, date_to)

    summary = df.group_by("persona").agg(
        money(pl.col("monto").sum()).alias("total")
    ).sort("persona")

    if summary.is_empty():
        return _empty_fig()

    fig = go.Figure(data=[
        go.Bar(x=summary["persona"], y=summary["total"], marker_color=["#1f77b4", "#ff7f0e"])
    ])
    fig.update_layout(
        title="Comparativa de Gastos Variables",
        xaxis_title="Persona",
        yaxis_title="Monto Total",
        hovermode="x unified"
    )
    return fig


def tipo_gasto_por_categoria(
    rows: list[dict],
    tipo_filter=None,
    date_from=None,
    date_to=None,
) -> go.Figure:
    """Grouped bar chart: amount per category per persona, filtered by tipo_de_gasto."""
    if not rows:
        return _empty_fig()

    df = pl.DataFrame(rows)

    if tipo_filter:
        df = df.filter(pl.col("tipo_de_gasto") == tipo_filter)

    df = _filter_dates(df, date_from, date_to)

    if df.is_empty():
        return _empty_fig()

    summary = (
        df.with_columns(pl.col("monto").cast(pl.Float64))
        .group_by(["categoria", "persona"])
        .agg(money(pl.col("monto").sum()).alias("total"))
        .sort(["categoria", "persona"])
    )

    personas = sorted(summary["persona"].unique().to_list())
    categorias = sorted(summary["categoria"].unique().to_list())
    colors = {"Marco": "steelblue", "Chiara": "coral"}

    fig = go.Figure()
    for persona in personas:
        p_df = summary.filter(pl.col("persona") == persona)
        p_map = dict(zip(p_df["categoria"].to_list(), p_df["total"].to_list()))
        fig.add_trace(go.Bar(
            name=persona,
            x=categorias,
            y=[p_map.get(c, 0) for c in categorias],
            marker_color=colors.get(persona, "grey"),
        ))

    title = f"Tipo de Gasto por Categoría — {tipo_filter}" if tipo_filter else "Tipo de Gasto por Categoría"

    fig.update_layout(
        title=title,
        xaxis_title="Categoría",
        yaxis_title="Monto",
        barmode="group",
        hovermode="x unified",
        legend_title="Persona",
    )
    return fig


def gastos_fijos_por_gasto(gastos_fijos_rows: list[dict]) -> go.Figure:
    """Horizontal bar chart of fixed expense amounts by name."""
    if not gastos_fijos_rows:
        return _empty_fig("Sin gastos fijos registrados")

    df = pl.DataFrame(gastos_fijos_rows).with_columns(money(pl.col("total"))).sort("total", descending=True)

    fig = go.Figure(data=[
        go.Bar(
            y=df["gasto"].to_list(),
            x=df["total"].to_list(),
            orientation="h",
            marker_color="coral",
            text=[f"${v:,.0f}" for v in df["total"].to_list()],
            textposition="outside",
        )
    ])
    fig.update_layout(
        title="Gastos Fijos por Concepto",
        xaxis_title="Monto",
        yaxis_title="",
        hovermode="y unified",
        margin=dict(l=150),
    )
    return fig
