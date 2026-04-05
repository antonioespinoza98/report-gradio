import polars as pl
from datetime import date

def to_display_df(rows: list[dict]) -> pl.DataFrame:
    """Convert raw rows to a Polars DataFrame for display in gr.Dataframe."""
    if not rows:
        return pl.DataFrame({
            "ID": [],
            "Persona": [],
            "Descripción": [],
            "Categoría": [],
            "Monto": [],
            "Fecha": [],
        })

    df = pl.DataFrame(rows)
    return df.select([
        pl.col("id").alias("ID"),
        pl.col("persona").alias("Persona"),
        pl.col("descripcion").alias("Descripción"),
        pl.col("categoria").alias("Categoría"),
        pl.col("monto").alias("Monto"),
        pl.col("fecha").alias("Fecha"),
    ])

def filter_df(rows: list[dict], persona=None, categoria=None, date_from=None, date_to=None) -> pl.DataFrame:
    """Filter rows and return a Polars DataFrame."""
    df = pl.DataFrame(rows) if rows else pl.DataFrame()

    if df.is_empty():
        return pl.DataFrame({
            "ID": [],
            "Persona": [],
            "Descripción": [],
            "Categoría": [],
            "Monto": [],
            "Fecha": [],
        })

    if persona:
        df = df.filter(pl.col("persona") == persona)
    if categoria:
        df = df.filter(pl.col("categoria") == categoria)
    if date_from:
        df = df.filter(pl.col("fecha") >= date_from)
    if date_to:
        df = df.filter(pl.col("fecha") <= date_to)

    return df.select([
        pl.col("id").alias("ID"),
        pl.col("persona").alias("Persona"),
        pl.col("descripcion").alias("Descripción"),
        pl.col("categoria").alias("Categoría"),
        pl.col("monto").alias("Monto"),
        pl.col("fecha").alias("Fecha"),
    ])
