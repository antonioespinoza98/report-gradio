---
name: gradio
description: Patrones de Gradio (Blocks, componentes, eventos, estado, layout) adaptados a cómo está estructurada la UI de este repo. Usalo al crear o modificar pestañas, formularios, tablas o gráficos en ui/.
---

# Gradio en este proyecto

## Estructura obligatoria

- Una pestaña = un módulo `ui/tab_<nombre>.py` con una función `build_tab()`. Se importa en `ui/__init__` implícitamente (`from ui import tab_x`) y se monta en `app.py` dentro de `gr.Tabs()` con `gr.Tab(label="N️⃣ ...", id="tab_<nombre>")`.
- La UI no habla con la base: llama a `models/*` para datos y a `transforms/*` para armar DataFrames y figuras. No metas SQL ni lógica de agregación en `ui/`.
- Si los datos de la pestaña pueden cambiar desde otra pestaña, `build_tab()` devuelve `(fn_refresco, inputs, outputs)` y `app.py` los conecta con `tab.select(fn=..., inputs=..., outputs=...)`. Seguí este patrón; no cargues solo al arrancar.

```python
# ui/tab_ejemplo.py
def build_tab():
    gr.Markdown("### Título que diga la conclusión")
    plot = gr.Plot(value=_figura_inicial(), label="Gasto por periodo")

    def refrescar(grano):
        return _figura(grano)

    return refrescar, [grano_dd], [plot]

# app.py
with gr.Tab(label="8️⃣ Ejemplo", id="tab_ejemplo") as tab8:
    fn, ins, outs = tab_ejemplo.build_tab()
tab8.select(fn=fn, inputs=ins, outputs=outs)
```

## Reglas

1. **Carga inicial tolerante a fallos**: envolvé la lectura inicial en `try/except` y caé a un DataFrame vacío (`to_display_df([])`), como hacen `tab_viajes.py` y `tab_ingresar_gasto.py`. La página no debe romperse si la base no responde.
2. **Serialización**: los valores por defecto de `gr.Dataframe`, `gr.Plot`, etc. deben ser JSON-serializables. `Decimal` rompe toda la página; por eso `db/connection.py` convierte `NUMERIC` a `float`. No lo desactives.
3. **Errores al usuario**: usá `raise gr.Error("mensaje en español")` o `gr.Warning(...)`. Instanciar `gr.Error(...)` sin `raise` no muestra nada (bug conocido en `on_save_click`). Si falla, devolvé `gr.update()` en las salidas para no borrar lo que el usuario escribió.
4. **Eventos**: `.click()`, `.change()`, `.select()`. Mantené el número de `outputs` igual al de valores que devuelve la función.
5. **Layout**: `gr.Group()` + `gr.Row()` para formularios; `gr.Tabs()` anidadas para subsecciones (ver `tab_tablas.py`). Máximo 3-4 controles por fila.
6. **Tablas**: `gr.Dataframe(value=df, interactive=False, label=...)` con DataFrames de Polars que ya traen columnas en español (`Persona`, `Monto`, `Fecha`...). El renombrado vive en `transforms/`.
7. **Gráficos**: `gr.Plot(value=fig)` con figuras de Plotly (`plotly.graph_objects`) construidas en `transforms/visualizaciones.py` o `transforms/metricas.py`. Ver skill `eleccion-de-graficos`.
8. **Textos de usuario en español**, nombres de variables y funciones en el estilo del módulo vecino (mezcla actual: nombres de dominio en español, helpers en inglés/español). Docstrings y comentarios en español.
9. **Estado**: el proyecto no usa `gr.State`; el estado es la base de datos. Antes de introducir `gr.State`, comprobá que no baste con releer en `tab.select`.
10. Cambiar el contenido de una lista desplegable: `gr.update(choices=..., value=...)` (ver `refresh_viajes`).

## Verificar

`python app.py` y abrir `http://localhost:7860`. Recorré la pestaña modificada y las que comparten datos con ella. Versión local de Gradio: 6.x; el Space declara 5.25.0 en el README, por lo que conviene evitar APIs que solo existan en una de las dos.
