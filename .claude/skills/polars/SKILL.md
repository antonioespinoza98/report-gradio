---
name: polars
description: Uso idiomático de Polars (expresiones, LazyFrame, joins, ventanas, rendimiento) con ejemplos basados en los datos de gastos de este repo. Usalo al escribir o refactorizar código en transforms/ o al procesar filas de la base.
---

# Polars en este proyecto

Versión instalada: 1.43. Los datos entran como `list[dict]` desde `models/*` y se convierten con `pl.DataFrame(rows)`. Columnas de `gastos_variables`: `persona`, `descripcion`, `categoria`, `monto` (float), `fecha` (date), `tipo_de_gasto`, `viaje_id`, `viaje_nombre`, `created_at`.

## Reglas

1. **Expresiones, no bucles**: nada de `map_elements`, `apply`, `iter_rows` ni `for` sobre filas para calcular. Si lo parece necesario, buscá la expresión nativa (`when/then`, `str.*`, `dt.*`).
2. **Elegí columnas pronto**: `pl.DataFrame(rows).select([...])` solo con lo que usarás.
3. **Dinero**: después de `sum`/`mean`/restas, `money(expr)` de `utils/money.py` (redondea a céntimos y normaliza `-0.0`). Para guardar o validar, `Decimal` o céntimos enteros, no float.
4. **`LazyFrame`** (`.lazy()` ... `.collect()`) cuando encadenes varios pasos o leas mucho; con ~600 filas no es necesario, pero no cuesta y deja a Polars optimizar. No lo uses para forzar complejidad.
5. **Esquema explícito** si la lista puede venir vacía (un `pl.DataFrame([])` no tiene columnas): ver `_PERIODOS_COLS` en `transforms/metricas.py` y `to_display_df([])` en `transforms/gastos.py`.
6. **Nulos**: `fill_null("")` para mostrar (`viaje_nombre`), `drop_nulls` solo si es intencional. `categoria_id` es NULL en ~40 % de las filas.
7. **Joins** con `how="left"` y claves explícitas; comprobá que no multiplican filas (`validate="m:1"`).
8. **Ordená** de forma determinista antes de `shift`/`over` o de mostrar.

## Ejemplos

Total y media por categoría y persona (en una sola pasada):

```python
resumen = (
    df.group_by(["categoria", "persona"])
    .agg(
        money(pl.col("monto").sum()).alias("total"),
        pl.len().alias("n"),
        money(pl.col("monto").median()).alias("mediana"),
    )
    .sort("total", descending=True)
)
```

Ventana: participación de cada categoría en el total del mes, sin join ni bucle:

```python
participacion = (
    df.with_columns(pl.col("fecha").dt.truncate("1mo").alias("mes"))
    .group_by(["mes", "categoria"]).agg(pl.col("monto").sum().alias("total"))
    .with_columns((pl.col("total") / pl.col("total").sum().over("mes")).alias("pct"))
)
```

Acumulado y variación mensual:

```python
mensual = (
    df.group_by(pl.col("fecha").dt.truncate("1mo").alias("mes"))
    .agg(pl.col("monto").sum().alias("total"))
    .sort("mes")
    .with_columns(
        pl.col("total").cum_sum().alias("acumulado"),
        pl.col("total").pct_change().alias("variacion"),
    )
)
```

Patrón de condición (en lugar de `if` por fila), tomado de `por_periodo`:

```python
pl.when(pl.col("fin") < hoy).then(pl.lit("Completo"))
 .when(pl.col("inicio") > hoy).then(pl.lit("Futuro"))
 .otherwise(pl.lit("En curso"))
```

## Rendimiento

- Hoy `get_all()` trae toda la tabla en cada pestaña. Si crece, filtrá/agregá en SQL (`date_trunc`, `GROUP BY`) y dejá a Polars lo que no se pueda expresar en SQL.
- Para detectar cuellos de botella: `lf.explain()` y medí con `time.perf_counter()` antes de optimizar.
- Evitá convertir a pandas.
