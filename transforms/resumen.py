import polars as pl
from decimal import Decimal

def calc_resumen(
    ingresos_rows: list[dict],
    gastos_rows: list[dict],
    responsable_rows: list[dict],
    gastos_fijos_rows: list[dict],
) -> pl.DataFrame:
    from utils.constants import PERSONAS

    zero = Decimal(0)

    # --- Ingresos: one row per persona, total is already the full income ---
    if ingresos_rows:
        ingresos_df = pl.DataFrame(ingresos_rows).select(
            pl.col("persona"), pl.col("total").cast(pl.Float64).alias("ingreso_total")
        )
    else:
        ingresos_df = pl.DataFrame({"persona": PERSONAS, "ingreso_total": [0.0, 0.0]})

    # --- Gastos variables: sum monto per persona ---
    if gastos_rows:
        gastos_df = pl.DataFrame(gastos_rows)
        gastos_summary = gastos_df.group_by("persona").agg(
            pl.col("monto").cast(pl.Float64).sum().alias("gasto_variable")
        )
    else:
        gastos_summary = pl.DataFrame({"persona": PERSONAS, "gasto_variable": [0.0, 0.0]})

    # --- Gastos fijos: join gastos_fijos with responsable_gastos on gasto name,
    #     use gastos_fijos.total as the amount, group by responsable ---
    fijos_names = {r["gasto"] for r in gastos_fijos_rows}
    fijos_lookup = {r["gasto"]: float(r["total"]) for r in gastos_fijos_rows}

    fijos_por_persona: dict[str, float] = {p: 0.0 for p in PERSONAS}
    for r in responsable_rows:
        if r["gasto"] in fijos_names:
            persona = r["responsable"]
            if persona in fijos_por_persona:
                fijos_por_persona[persona] += fijos_lookup[r["gasto"]]

    fijos_summary = pl.DataFrame({
        "persona": list(fijos_por_persona.keys()),
        "gasto_fijo": list(fijos_por_persona.values()),
    })

    # --- Join all three and compute sobrante ---
    result = (
        ingresos_df
        .join(gastos_summary, on="persona", how="left")
        .join(fijos_summary, on="persona", how="left")
        .fill_null(0.0)
        .with_columns(
            (pl.col("ingreso_total") - pl.col("gasto_variable") - pl.col("gasto_fijo")).alias("sobrante")
        )
    )

    return result.select([
        pl.col("persona").alias("Persona"),
        pl.col("ingreso_total").alias("Ingreso"),
        pl.col("gasto_variable").alias("Gasto Variable"),
        pl.col("gasto_fijo").alias("Gasto Fijo"),
        pl.col("sobrante").alias("Sobrante"),
    ])
