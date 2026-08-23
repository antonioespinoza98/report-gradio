import polars as pl

# Sentinel value used by the "Viaje" dropdown when no trip is selected.
# Gradio dropdowns handle None values poorly, so 0 stands in for "sin viaje".
NINGUNO = 0
NINGUNO_LABEL = "— ninguno —"

_EMPTY = {
    "ID": [],
    "Nombre": [],
    "Destino": [],
    "Desde": [],
    "Hasta": [],
}

def label(row: dict) -> str:
    """Human-readable label for a trip."""
    destino = row.get("destino")
    base = f"{row['nombre']} ({destino})" if destino else row["nombre"]
    return f"{base} · {row['fecha_inicio']} → {row['fecha_fin']}"

def to_choices(rows: list[dict]) -> list[tuple[str, int]]:
    """Build Gradio dropdown choices, with 'ninguno' first."""
    return [(NINGUNO_LABEL, NINGUNO)] + [(label(r), r["id"]) for r in rows]

def to_display_df(rows: list[dict]) -> pl.DataFrame:
    """Convert raw trip rows to a Polars DataFrame for display in gr.Dataframe."""
    if not rows:
        return pl.DataFrame(_EMPTY)

    df = pl.DataFrame(rows)
    return df.select([
        pl.col("id").alias("ID"),
        pl.col("nombre").alias("Nombre"),
        pl.col("destino").alias("Destino"),
        pl.col("fecha_inicio").alias("Desde"),
        pl.col("fecha_fin").alias("Hasta"),
    ])
