import polars as pl
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def gastos_por_categoria(rows: list[dict], persona_filter=None, date_from=None, date_to=None) -> go.Figure:
    """Create a bar chart of expenses by category."""
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    df = pl.DataFrame(rows)

    # Filter by persona if specified (and it's not "Ambos")
    if persona_filter and persona_filter != "Ambos":
        df = df.filter(pl.col("persona") == persona_filter)

    # Filter by date range
    if date_from:
        df = df.filter(pl.col("fecha") >= date_from)
    if date_to:
        df = df.filter(pl.col("fecha") <= date_to)

    # Group by categoria and sum
    summary = df.group_by("categoria").agg(
        pl.col("monto").sum().alias("total")
    ).sort("total", descending=True)

    if summary.is_empty():
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    fig = go.Figure(data=[
        go.Bar(x=summary["categoria"], y=summary["total"], marker_color="steelblue")
    ])
    fig.update_layout(
        title="Gastos por Categoría",
        xaxis_title="Categoría",
        yaxis_title="Monto",
        hovermode="x unified"
    )
    return fig

def gastos_en_tiempo(rows: list[dict], date_from=None, date_to=None) -> go.Figure:
    """Create a line chart of spending over time (by month)."""
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    df = pl.DataFrame(rows)

    # Filter by date range
    if date_from:
        df = df.filter(pl.col("fecha") >= date_from)
    if date_to:
        df = df.filter(pl.col("fecha") <= date_to)

    if df.is_empty():
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    # Extract year-month and group
    df = df.with_columns([
        (pl.col("fecha").dt.strftime("%Y-%m")).alias("year_month")
    ])
    summary = df.group_by("year_month").agg(
        pl.col("monto").sum().alias("total")
    ).sort("year_month")

    fig = go.Figure(data=[
        go.Scatter(x=summary["year_month"], y=summary["total"], mode="lines+markers", line_color="darkblue")
    ])
    fig.update_layout(
        title="Gastos en el Tiempo",
        xaxis_title="Período",
        yaxis_title="Monto Total",
        hovermode="x"
    )
    return fig

def comparativa_personas(rows: list[dict], date_from=None, date_to=None) -> go.Figure:
    """Create a side-by-side bar chart comparing two personas."""
    if not rows:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    df = pl.DataFrame(rows)

    # Filter by date range
    if date_from:
        df = df.filter(pl.col("fecha") >= date_from)
    if date_to:
        df = df.filter(pl.col("fecha") <= date_to)

    # Group by persona
    summary = df.group_by("persona").agg(
        pl.col("monto").sum().alias("total")
    ).sort("persona")

    if summary.is_empty():
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    fig = go.Figure(data=[
        go.Bar(x=summary["persona"], y=summary["total"], marker_color=["#1f77b4", "#ff7f0e"])
    ])
    fig.update_layout(
        title="Comparativa de Gastos",
        xaxis_title="Persona",
        yaxis_title="Monto Total",
        hovermode="x unified"
    )
    return fig

def fijos_vs_variables(gastos_fijos_rows: list[dict], gastos_var_rows: list[dict]) -> go.Figure:
    """Create a stacked bar chart comparing fixed vs variable expenses by month."""
    if not gastos_var_rows:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False)
        return fig

    df_var = pl.DataFrame(gastos_var_rows)

    # Extract year-month and group variable expenses
    df_var = df_var.with_columns([
        (pl.col("fecha").dt.strftime("%Y-%m")).alias("year_month")
    ])
    var_summary = df_var.group_by("year_month").agg(
        pl.col("monto").sum().alias("variables")
    ).sort("year_month")

    # Compute total fixed expenses
    if gastos_fijos_rows:
        df_fijos = pl.DataFrame(gastos_fijos_rows)
        total_fixed = df_fijos["total"].sum()
    else:
        total_fixed = 0

    # Add fixed to each month
    var_summary = var_summary.with_columns([
        pl.lit(total_fixed).alias("fijos")
    ])

    fig = go.Figure(data=[
        go.Bar(x=var_summary["year_month"], y=var_summary["fijos"], name="Gastos Fijos", marker_color="coral"),
        go.Bar(x=var_summary["year_month"], y=var_summary["variables"], name="Gastos Variables", marker_color="steelblue")
    ])
    fig.update_layout(
        title="Gastos Fijos vs Variables",
        xaxis_title="Período",
        yaxis_title="Monto",
        barmode="stack",
        hovermode="x unified"
    )
    return fig
