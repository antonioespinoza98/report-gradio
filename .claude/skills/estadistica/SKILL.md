---
name: estadistica
description: Estadística descriptiva sencilla para gastos personales (media, mediana, percentiles, dispersión, mínimos y máximos, outliers, totales y variaciones período a período). Usalo al calcular métricas o resúmenes. No cubre inferencia ni intervalos de confianza.
---

# Estadística descriptiva para gastos personales

Alcance: **solo descriptiva**. Nada de pruebas de hipótesis, p-valores, intervalos de confianza ni modelos predictivos. Si hace falta algo de eso, decilo y no lo improvises.

## Qué calcular y cuándo

| Medida | Úsala para | Cuidado |
|---|---|---|
| Total (`sum`) | Cuánto se gastó en un periodo/categoría | Es la medida base; exacta en SQL con `numeric` |
| Media | Gasto típico por periodo cuando no hay valores extremos | Un gasto grande (viaje, alquiler anual) la distorsiona |
| **Mediana** | Gasto típico de una compra o de un periodo con asimetría | **Preferila a la media** en gastos: la distribución es muy asimétrica (muchas compras chicas, pocas enormes) |
| Percentiles (p25, p75, p90) | Rango habitual y "compra grande" | Con pocos datos (<20) son poco estables |
| Mín / Máx | Extremos con su fecha y descripción | Mostrá siempre qué compra o periodo es |
| Desvío estándar / rango intercuartílico (IQR) | Qué tan regular es el gasto | IQR (p75 − p25) resiste mejor los extremos |
| Variación período a período | Cambio frente al periodo anterior | Solo entre periodos completos |

Regla práctica: si media y mediana difieren más de ~20 %, reportá la mediana y mencioná la media.

## Outliers (criterio simple)

Un gasto es atípico si cae fuera de `[p25 − 1,5·IQR, p75 + 1,5·IQR]`. Marcalo, no lo borres: puede ser un gasto legítimo (un viaje). Mostrá el valor, la fecha y la descripción.

## Variación

- Absoluta: `actual − anterior` (en €).
- Relativa: `(actual − anterior) / anterior`. Si `anterior == 0`, devolvé "—", no infinito.
- Compará solo periodos completos. Un mes en curso se compara por día equivalente o se excluye. `transforms/metricas.py::por_periodo` ya clasifica cada periodo en `Completo`, `En curso` o `Futuro`; reutilizalo.

## Ejemplo con Polars (datos reales del repo)

```python
import polars as pl
from utils.money import money

df = pl.DataFrame(rows).select(["fecha", "categoria", "monto"])

mensual = (
    df.with_columns(pl.col("fecha").dt.truncate("1mo").alias("mes"))
    .group_by("mes").agg(money(pl.col("monto").sum()).alias("total"))
    .sort("mes")
    .with_columns(
        (pl.col("total") / pl.col("total").shift(1) - 1).alias("variacion")
    )
)

resumen = df.select(
    money(pl.col("monto").median()).alias("mediana"),
    money(pl.col("monto").mean()).alias("media"),
    pl.col("monto").quantile(0.25).alias("p25"),
    pl.col("monto").quantile(0.75).alias("p75"),
    pl.col("monto").max().alias("maximo"),
)
```

## Reglas del proyecto

- Redondeá con `utils.money.money()` después de agregar; los floats acumulan error (`1234.5600000000002`).
- Contá cuántos datos hay (`n`) y mostralo junto a cualquier promedio o percentil.
- Un solo mes con ~100 gastos no permite hablar de "tendencia". Con menos de 3 periodos completos, mostrá valores, no tendencias.
- Separá `Gasto Común` de `Gasto Personal` y por `persona` antes de comparar personas.
