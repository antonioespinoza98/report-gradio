import polars as pl
import plotly.graph_objects as go
from datetime import date as date_type

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


def gastos_por_categoria(rows: list[dict], persona_filter=None, date_from=None, date_to=None) -> go.Figure:
    """Bar chart of expenses by category."""
    if not rows:
        return _empty_fig()

    df = pl.DataFrame(rows)

    if persona_filter and persona_filter != "Ambos":
        df = df.filter(pl.col("persona") == persona_filter)

    df = _filter_dates(df, date_from, date_to)

    summary = df.group_by("categoria").agg(
        pl.col("monto").sum().alias("total")
    ).sort("total", descending=True)

    if summary.is_empty():
        return _empty_fig()

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
        pl.col("monto").sum().alias("total")
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
        pl.col("monto").sum().alias("total")
    ).sort("persona")

    if summary.is_empty():
        return _empty_fig()

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
        df.group_by(["categoria", "persona"])
        .agg(pl.col("monto").sum().alias("total"))
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

    df = pl.DataFrame(gastos_fijos_rows).sort("total", descending=True)

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


def estado_pagos_mes(
    pagos_fijos_rows: list[dict],
    gastos_fijos_rows: list[dict],
    responsable_rows: list[dict] | None = None,
) -> go.Figure:
    """Heatmap showing payment status per expense per person.

    Cells where the persona is not responsible (based on responsable_gastos)
    are shown in grey with 'N/A' instead of 'Pendiente'.
    """
    if not pagos_fijos_rows or not gastos_fijos_rows:
        return _empty_fig("Sin datos de pagos para este período")

    # Build a set of responsible personas per gasto.
    # Handles multiple rows for the same gasto (e.g. one row per persona instead of "Ambos").
    resp_set: dict[str, set] = {}
    if responsable_rows:
        for r in responsable_rows:
            key = r["gasto"].strip()
            if key not in resp_set:
                resp_set[key] = set()
            if r["responsable"] == "Ambos":
                resp_set[key].update(["Marco", "Chiara"])
            else:
                resp_set[key].add(r["responsable"])

    gf_df = pl.DataFrame(gastos_fijos_rows).select(["id", "gasto"])
    pf_df = pl.DataFrame(pagos_fijos_rows)
    merged = pf_df.join(gf_df, left_on="gasto_fijo_id", right_on="id")

    gastos_names = sorted(merged["gasto"].unique().to_list())
    personas = sorted(merged["persona"].unique().to_list())

    # z values: None = N/A, 0 = Pendiente, 1 = Pagado
    z = []
    text = []
    for persona in personas:
        persona_df = merged.filter(pl.col("persona") == persona)
        paid_map = {r["gasto"]: r["pagado"] for r in persona_df.to_dicts()}

        row_z = []
        row_text = []
        for g in gastos_names:
            responsible = resp_set.get(g)
            # N/A if we know who's responsible and this persona is not in that set
            if responsible and persona not in responsible:
                row_z.append(None)
                row_text.append("N/A")
            elif paid_map.get(g, False):
                row_z.append(1)
                row_text.append("Pagado")
            else:
                row_z.append(0)
                row_text.append("Pendiente")
        z.append(row_z)
        text.append(row_text)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=gastos_names,
        y=personas,
        zmin=0,
        zmax=1,
        colorscale=[[0, "#e74c3c"], [1, "#2ecc71"]],
        showscale=False,
        text=text,
        texttemplate="%{text}",
        hovertemplate="%{y} — %{x}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title="Estado de Pagos del Mes",
        xaxis_title="",
        yaxis_title="",
        xaxis=dict(side="bottom"),
    )
    return fig


def estado_ahorros_mes(
    pagos_ahorros_rows: list[dict],
    ahorros_rows: list[dict],
    responsable_rows: list[dict] | None = None,
) -> go.Figure:
    """Heatmap showing savings deposit status per ahorro per person.

    Uses responsable_gastos (matched by name against ahorros.ahorro) to mark
    cells N/A for personas who are not responsible for a given ahorro.
    """
    if not pagos_ahorros_rows or not ahorros_rows:
        return _empty_fig("Sin datos de ahorros para este período")

    # Build a set of responsible personas per ahorro (same logic as estado_pagos_mes).
    resp_set: dict[str, set] = {}
    if responsable_rows:
        for r in responsable_rows:
            key = r["gasto"].strip()
            if key not in resp_set:
                resp_set[key] = set()
            if r["responsable"] == "Ambos":
                resp_set[key].update(["Marco", "Chiara"])
            else:
                resp_set[key].add(r["responsable"])

    ah_df = pl.DataFrame(ahorros_rows).select(["id", "ahorro"])
    pa_df = pl.DataFrame(pagos_ahorros_rows)
    merged = pa_df.join(ah_df, left_on="ahorro_id", right_on="id")

    ahorro_names = sorted(merged["ahorro"].unique().to_list())
    personas = sorted(merged["persona"].unique().to_list())

    z = []
    text = []
    for persona in personas:
        persona_df = merged.filter(pl.col("persona") == persona)
        paid_map = {r["ahorro"]: r["pagado"] for r in persona_df.to_dicts()}

        row_z = []
        row_text = []
        for a in ahorro_names:
            responsible = resp_set.get(a)
            if responsible and persona not in responsible:
                row_z.append(None)
                row_text.append("N/A")
            elif paid_map.get(a, False):
                row_z.append(1)
                row_text.append("Depositado")
            else:
                row_z.append(0)
                row_text.append("Pendiente")
        z.append(row_z)
        text.append(row_text)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=ahorro_names,
        y=personas,
        zmin=0,
        zmax=1,
        colorscale=[[0, "#e74c3c"], [1, "#2ecc71"]],
        showscale=False,
        text=text,
        texttemplate="%{text}",
        hovertemplate="%{y} — %{x}: %{text}<extra></extra>",
    ))
    fig.update_layout(
        title="Estado de Depósitos de Ahorro del Mes",
        xaxis_title="",
        yaxis_title="",
        xaxis=dict(side="bottom"),
    )
    return fig


def fijos_vs_variables(gastos_fijos_rows: list[dict], gastos_var_rows: list[dict]) -> go.Figure:
    """Stacked bar chart: fixed vs variable expenses by month."""
    if not gastos_var_rows:
        return _empty_fig()

    df_var = pl.DataFrame(gastos_var_rows)
    df_var = df_var.with_columns(
        pl.col("fecha").dt.strftime("%Y-%m").alias("year_month")
    )
    var_summary = df_var.group_by("year_month").agg(
        pl.col("monto").sum().alias("variables")
    ).sort("year_month")

    total_fixed = pl.DataFrame(gastos_fijos_rows)["total"].sum() if gastos_fijos_rows else 0

    var_summary = var_summary.with_columns(pl.lit(total_fixed).alias("fijos"))

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
