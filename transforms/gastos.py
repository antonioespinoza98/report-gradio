import polars as pl
from datetime import date

def _parse_date(d):
    if d is None:
        return None
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except Exception:
        return None

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
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    if d_from:
        df = df.filter(pl.col("fecha") >= d_from)
    if d_to:
        df = df.filter(pl.col("fecha") <= d_to)

    return df.select([
        pl.col("id").alias("ID"),
        pl.col("persona").alias("Persona"),
        pl.col("descripcion").alias("Descripción"),
        pl.col("categoria").alias("Categoría"),
        pl.col("monto").alias("Monto"),
        pl.col("fecha").alias("Fecha"),
    ])
