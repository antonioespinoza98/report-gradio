import polars as pl

# Amounts are money: two decimals. Values read from the DB are already exact,
# but sums and subtractions in float can drift (e.g. 1234.5600000000002), so
# every aggregated or displayed amount goes through these helpers.
MONEY_DP = 2

def round_money(value):
    """Round a scalar amount to cents. Tolerates None."""
    if value is None:
        return None
    rounded = round(float(value), MONEY_DP)
    # Drift in a subtraction can land on -0.0, which would display as "-0.00".
    return 0.0 if rounded == 0 else rounded

def money(expr: pl.Expr) -> pl.Expr:
    """Round a Polars amount expression to cents, normalising -0.0 to 0.0."""
    rounded = expr.round(MONEY_DP)
    return pl.when(rounded == 0).then(pl.lit(0.0)).otherwise(rounded)
