import polars as pl
from decimal import Decimal

def calc_resumen(ingresos_rows: list[dict], gastos_rows: list[dict], responsable_rows: list[dict]) -> pl.DataFrame:
    """
    Calculate the Resumen tab summary.

    Returns a DataFrame with columns: (Persona, Ingreso, Total Gasto, Sobrante)

    Logic:
    1. Sum ingresos by persona
    2. Sum gastos_variables by persona (from gastos_rows)
    3. Join and compute sobrante = ingreso - gasto
    """
    from utils.constants import PERSONAS

    # Build ingresos DataFrame
    if ingresos_rows:
        ingresos_df = pl.DataFrame(ingresos_rows)
        ingresos_summary = ingresos_df.group_by("persona").agg(
            pl.col("total").sum().alias("ingreso_total")
        )
    else:
        ingresos_summary = pl.DataFrame({
            "persona": PERSONAS,
            "ingreso_total": [Decimal(0), Decimal(0)]
        })

    # Build gastos DataFrame (from gastos_variables which are passed in gastos_rows)
    if gastos_rows:
        gastos_df = pl.DataFrame(gastos_rows)
        gastos_summary = gastos_df.group_by("persona").agg(
            pl.col("monto").sum().alias("gasto_total")
        )
    else:
        gastos_summary = pl.DataFrame({
            "persona": PERSONAS,
            "gasto_total": [Decimal(0), Decimal(0)]
        })

    # Ensure both have all personas
    for persona in PERSONAS:
        if persona not in ingresos_summary["persona"].to_list():
            ingresos_summary = ingresos_summary.vstack(
                pl.DataFrame({"persona": [persona], "ingreso_total": [Decimal(0)]})
            )
        if persona not in gastos_summary["persona"].to_list():
            gastos_summary = gastos_summary.vstack(
                pl.DataFrame({"persona": [persona], "gasto_total": [Decimal(0)]})
            )

    # Join
    result = ingresos_summary.join(gastos_summary, on="persona", how="outer")

    # Compute sobrante
    result = result.with_columns([
        (pl.col("ingreso_total") - pl.col("gasto_total")).alias("sobrante")
    ])

    # Format for display
    return result.select([
        pl.col("persona").alias("Persona"),
        pl.col("ingreso_total").alias("Ingreso"),
        pl.col("gasto_total").alias("Total Gasto"),
        pl.col("sobrante").alias("Sobrante"),
    ])
