import polars as pl

# Amounts are money: two decimals. Values read from the DB are already exact,
# but sums and subtractions in float can drift (e.g. 1234.5600000000002), so
# every aggregated or displayed amount goes through this helper.
MONEY_DP = 2

def money(expr: pl.Expr) -> pl.Expr:
    """Round a Polars amount expression to cents.

    Drift in a sum or subtraction can land on -0.0, which would display as
    "-0.00", so exact zero is normalised.
    """
    rounded = expr.round(MONEY_DP)
    return pl.when(rounded == 0).then(pl.lit(0.0)).otherwise(rounded)
