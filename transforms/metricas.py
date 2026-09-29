import polars as pl
import plotly.graph_objects as go
from datetime import date
from utils.money import money

# Grain label -> Polars truncation interval. Weeks truncate to Monday.
GRANOS = {
    "Diario": "1d",
    "Semanal": "1w",
    "Mensual": "1mo",
    "Anual": "1y",
}

_PERIODOS_COLS = {
    "Periodo": [], "Total": [], "Nº gastos": [], "Ticket promedio": [], "Estado": [],
}

def _fin(inicio: pl.Expr, every: str) -> pl.Expr:
    """Last calendar day covered by a period that starts at `inicio`."""
    if every == "1d":
        return inicio
    if every == "1w":
        return inicio.dt.offset_by("6d")
    return inicio.dt.offset_by(every).dt.offset_by("-1d")

def _etiqueta(grano: str) -> pl.Expr:
    """Human-readable label for each period bucket."""
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
    Aggregate expenses into buckets of the given grain.

    A period counts as complete only once its last day has passed, so the
    running period (and any future-dated rows) are marked 'En curso' and kept
    out of the statistics.
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

    return (
        agg.with_columns(_fin(pl.col("inicio"), every).alias("fin"))
        .with_columns((pl.col("fin") < hoy).alias("completo"))
        .with_columns(
            pl.when(pl.col("fin") < hoy).then(pl.lit("Completo"))
            .when(pl.col("inicio") > hoy).then(pl.lit("Futuro"))
            .otherwise(pl.lit("En curso"))
            .alias("estado")
        )
        .with_columns(_etiqueta(grano).alias("periodo"))
    )

def a_tabla(per: pl.DataFrame) -> pl.DataFrame:
    """Per-period table for display."""
    if per.is_empty():
        return pl.DataFrame(_PERIODOS_COLS)
    return per.select([
        pl.col("periodo").alias("Periodo"),
        pl.col("total").alias("Total"),
        pl.col("n").alias("Nº gastos"),
        pl.col("ticket").alias("Ticket promedio"),
        pl.col("estado").alias("Estado"),
    ])

def _num(v) -> str:
    return "—" if v is None else f"{float(v):,.2f}"

def _extremo(per: pl.DataFrame, col: str, mayor: bool) -> str:
    if per.is_empty():
        return "—"
    fila = per.sort(col, descending=mayor).row(0, named=True)
    return f"{fila['periodo']} · {_num(fila[col])}"

def _gasto_extremo(rows: list[dict], mayor: bool) -> str:
    if not rows:
        return "—"
    fila = sorted(rows, key=lambda r: float(r["monto"]), reverse=mayor)[0]
    return f"{fila['descripcion']} ({fila['fecha']}) · {_num(fila['monto'])}"

def _futuros(futuros: pl.DataFrame) -> str:
    """Future-dated rows are excluded too; surface them so they aren't silent."""
    if futuros.is_empty():
        return "—"
    return f"{int(futuros['n'].sum())} gasto(s) · {_num(futuros['total'].sum())}"

def resumen(rows: list[dict], grano: str, hoy: date | None = None) -> pl.DataFrame:
    """
    Headline metrics for the selected grain.

    'Total gastado' covers every row in range. The average, median, min and max
    are computed over complete periods only.
    """
    hoy = hoy or date.today()
    per = por_periodo(rows, grano, hoy)
    if per.is_empty():
        completos = en_curso = futuros = per
    else:
        completos = per.filter(pl.col("estado") == "Completo")
        en_curso = per.filter(pl.col("estado") == "En curso")
        futuros = per.filter(pl.col("estado") == "Futuro")

    total = sum(float(r["monto"]) for r in rows) if rows else 0.0
    totales = completos["total"] if not completos.is_empty() else None

    metricas = [
        ("Total gastado (rango completo)", _num(total)),
        ("Nº de gastos", str(len(rows))),
        (f"Nº de periodos completos ({grano.lower()})", str(completos.height)),
        ("Promedio por periodo", _num(totales.mean()) if totales is not None else "—"),
        ("Mediana por periodo", _num(totales.median()) if totales is not None else "—"),
        ("Periodo más caro", _extremo(completos, "total", True)),
        ("Periodo más barato", _extremo(completos, "total", False)),
        ("Gasto individual más grande", _gasto_extremo(rows, True)),
        ("Gasto individual más pequeño", _gasto_extremo(rows, False)),
        ("Periodo en curso (excluido)", _extremo(en_curso, "total", True)),
        ("Gastos con fecha futura (excluidos)", _futuros(futuros)),
    ]

    return pl.DataFrame({
        "Métrica": [m for m, _ in metricas],
        "Valor": [v for _, v in metricas],
    })

def grafico(per: pl.DataFrame, grano: str) -> go.Figure:
    """Bar chart of period totals; the running period is shown in a muted colour."""
    if per.is_empty():
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles", showarrow=False,
                           xref="paper", yref="paper", x=0.5, y=0.5)
        return fig

    fig = go.Figure(data=[
        go.Bar(
            x=per["periodo"].to_list(),
            y=per["total"].to_list(),
            marker_color=["steelblue" if c else "lightgrey" for c in per["completo"].to_list()],
            hovertemplate="%{x}: %{y:,.2f}<extra></extra>",
        )
    ])
    fig.update_layout(
        title=f"Gasto por periodo — {grano}",
        xaxis_title="Periodo",
        yaxis_title="Monto",
        hovermode="x",
    )
    return fig
