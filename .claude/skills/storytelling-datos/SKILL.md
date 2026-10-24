---
name: storytelling-datos
description: Estructura narrativa para gráficos y dashboards de gastos (contexto, hallazgo, implicancia), títulos que dicen la conclusión y jerarquía visual. Usalo al diseñar o rediseñar una pestaña de visualización o al redactar títulos y anotaciones.
---

# Storytelling con los datos de gastos

## Estructura: contexto → hallazgo → implicancia

Cada gráfico o bloque responde las tres preguntas, en este orden:

1. **Contexto**: qué se mide, en qué periodo y para quién ("Gasto mensual de la pareja, abril-octubre 2026").
2. **Hallazgo**: lo que muestran los datos, con el número ("Restaurante subió 38 % en septiembre").
3. **Implicancia**: qué conviene mirar o decidir ("Es el 22 % del gasto variable: revisar antes de fijar presupuesto").

La implicancia es una sugerencia sobre los datos, no una afirmación causal. Con ~600 filas y 7 meses, no prometas tendencias.

## Títulos que dicen la conclusión

| En vez de | Escribí |
|---|---|
| "Gastos por categoría" | "Supermercado y Restaurante concentran el 55 % del gasto variable" |
| "Gasto en el tiempo" | "El gasto mensual se estabilizó cerca de 1.800 € desde junio" |
| "Marco vs Chiara" | "Chiara gasta 12 % más en gastos comunes" |

Reglas: máximo ~12 palabras; incluí el número clave con formato español (`1.234,56 €`, `38 %`); el título va en `gr.Markdown("### ...")` encima del `gr.Plot` o en el `title` de Plotly. El `label=` del componente queda como descripción neutra. Si el título depende de datos, generalo en `transforms/` a partir de los valores, nunca lo escribas a mano.

## Jerarquía visual

1. Primero los **números clave** (total del periodo, variación, mayor categoría) como tarjetas o tabla corta, como hace `tab_metricas.py`.
2. Después **un gráfico principal** que muestre el hallazgo; los secundarios van debajo o en otra pestaña.
3. Al final el **detalle** (tabla de filas).
4. Un solo color de énfasis para lo importante; todo lo demás en gris o tono neutro.
5. Etiquetá directamente (valores sobre las barras, nombre de la serie al final de la línea) en vez de depender de leyendas lejanas.
6. Quitá lo que no aporta: cuadrículas pesadas, bordes, decoraciones, ejes duplicados.

## Antes de entregar

- ¿Se entiende el mensaje en 5 segundos sin leer nada más?
- ¿El periodo "En curso" está marcado o excluido de promedios? (`transforms/metricas.py` ya separa Completo / En curso / Futuro; respetalo.)
- ¿Los montos están en euros y con formato español?
- ¿Hay datos insuficientes? Decilo en vez de dibujar un gráfico vacío.
