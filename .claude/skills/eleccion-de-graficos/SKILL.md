---
name: eleccion-de-graficos
description: Qué gráfico usar según la pregunta analítica y el tipo de variable (comparación, evolución, distribución, composición, relación), qué evitar, y cómo darle formato en español y euros con Plotly (1.234,56 €). Usalo al crear o cambiar cualquier figura.
---

# Elección de gráficos (Plotly + Gradio)

## Librería

**Plotly** (`plotly.graph_objects`, ya en `requirements.txt` y usado en `transforms/visualizaciones.py` y `transforms/metricas.py`), mostrado con `gr.Plot`. Motivos: interactividad (hover, zoom) sin código extra, soporte directo en Gradio y formato numérico configurable. No agregues matplotlib ni Altair. Los `gr.BarPlot`/`gr.LinePlot` nativos no se usan en este repo y dan menos control del formato.

## Pregunta → gráfico

| Pregunta | Variables | Gráfico |
|---|---|---|
| ¿Cuál es mayor? (categorías, personas) | categórica + monto | Barras horizontales ordenadas de mayor a menor |
| ¿Cómo evoluciona? | fecha + monto | Línea (pocos periodos: barras verticales por mes) |
| ¿Cómo se reparte el total? | categórica + monto | Barra apilada o barra única al 100 %; torta solo con ≤4 partes |
| ¿Cómo se distribuyen las compras? | monto individual | Histograma o caja (box) |
| ¿Qué cambió entre dos periodos? | categórica × 2 periodos | Barras agrupadas o diferencias |
| ¿Hay relación entre dos medidas? | dos numéricas | Dispersión (rara vez útil aquí) |
| ¿Cuánto se pagó de lo previsto? | bool por ítem | Tabla con estado o barras de progreso, no torta |

Lo que ya está en el repo (`Gastos en el Tiempo`, `Tipo de Gasto por Categoría`, `Gasto por periodo`) sirve de referencia; mantené el estilo.

## Qué evitar

- Ejes truncados en barras: las barras empiezan siempre en 0.
- Gráficos 3D, sombras, degradados.
- Tortas con más de 4-5 categorías (hay 11 categorías: usar barras).
- Paletas inaccesibles: no dependas solo del rojo/verde; usá una paleta apta para daltonismo (p. ej. `plotly.colors.qualitative.Safe`) y etiquetas directas. Contraste suficiente sobre fondo claro y oscuro.
- Doble eje Y y más de ~5 series en una línea.
- Dibujar el periodo "En curso" como si estuviera completo: distinguilo (otro tono o etiqueta).
- Gráficos vacíos: si no hay datos, mostrá un mensaje.

## Formato en español y euros

Plotly formatea con separadores configurables. Usá `separators=",."` (decimal coma, miles punto):

```python
import plotly.graph_objects as go

def formatear_eur(fig: go.Figure) -> go.Figure:
    """Euros en español: 1.234,56 €"""
    fig.update_layout(separators=",.")          # decimal ',' y miles '.'
    fig.update_yaxes(tickformat=",.0f", ticksuffix=" €")
    fig.update_traces(hovertemplate="%{x}<br>%{y:,.2f} €<extra></extra>")
    return fig
```

En barras horizontales el valor está en el eje X: aplicá `update_xaxes`. Para texto de valores: `texttemplate="%{x:,.0f} €"`.

Para cadenas fuera de Plotly (tablas, tarjetas, títulos) no uses `f"{x:,.2f}"` (da `1,234.56`, formato inglés, como hoy hace `_num` en `transforms/metricas.py`). Usá un helper único:

```python
def eur(valor) -> str:
    if valor is None:
        return "—"
    s = f"{float(valor):,.2f}"                      # 1,234.56
    return s.replace(",", "§").replace(".", ",").replace("§", ".") + " €"   # 1.234,56 €
```

Colocalo en `utils/money.py` (es de data-engineer: si no existe, pedíselo a la sesión principal con el nombre y la firma exactos). Fechas: `dd/mm/aaaa` para el usuario (`%d/%m/%Y`); meses en español en ejes con `ticktext` explícito si hace falta (`ene`, `feb`, ...), porque `strftime` depende del idioma del sistema. La base y los filtros siguen usando ISO `YYYY-MM-DD`.

## Checklist

Título con la conclusión (skill `storytelling-datos`), eje con unidad (€), barras desde 0, orden por valor, máximo ~6 colores, hover con valor formateado, datos vacíos manejados.
