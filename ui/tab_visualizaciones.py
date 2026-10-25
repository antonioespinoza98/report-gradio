from datetime import date

import gradio as gr

from models import gastos
from transforms import visualizaciones as viz
from ui import tab_visualizaciones_categoria


def build_tab():
    """Pestaña 'Visualizaciones': filtros compartidos + sub-tabs 'General' y 'por categoría'.

    Los filtros (persona, periodo, tipo de gasto) afectan a todos los gráficos. Una sola
    función `refrescar` lee la base una vez y alimenta ambos sub-tabs.
    Devuelve (fn, inputs, outputs); app.py la conecta a `tab.select`.
    """
    gr.Markdown("### Análisis de gastos variables")

    with gr.Group():
        with gr.Row():
            persona = gr.Radio(choices=viz.PERSONA_OPCIONES, value="Ambos", label="Persona")
            periodo = gr.Radio(choices=viz.PERIODOS, value="Últimos 3 meses", label="Periodo")
            tipo = gr.Dropdown(choices=viz.TIPO_OPCIONES, value=viz.TIPO_TODOS, label="Tipo de gasto")
    gr.Markdown(
        "Persona, periodo y tipo de gasto se aplican a todos los gráficos. "
        "«Últimos 3 meses» = 3 meses completos más el mes en curso. Algunos gráficos comparan "
        "a Marco con Chiara y lo indican en el propio gráfico."
    )
    gr.Markdown(f"*{viz.NOTA_REGISTRADO}*")
    refresh_button = gr.Button("🔄 Actualizar gráficas", variant="primary")

    with gr.Tabs():
        with gr.Tab(label="General", id="subtab_viz_general"):
            tarjetas = gr.Markdown("")
            plot_tiempo = gr.Plot(value=viz.figura_inicial(), label="Gasto mensual")
            plot_registrado = gr.Plot(value=viz.figura_inicial(), label="Registrado por persona")
        with gr.Tab(label="Visualizaciones - por categoría", id="subtab_viz_categoria"):
            cat_outputs, cat_calcular = tab_visualizaciones_categoria.build_tab()

    def refrescar(persona_sel, periodo_sel, tipo_sel):
        """Lee los gastos una sola vez y devuelve los valores de todos los sub-tabs."""
        hoy = date.today()
        desde, hasta = viz.rango_periodo(periodo_sel, hoy)
        try:
            # Trae a ambas personas siempre: las comparaciones ignoran el filtro de persona.
            rows = gastos.get_filtered(date_from=desde, date_to=hasta)
        except Exception:
            raise gr.Error("No se pudieron leer los gastos. Reintentá en unos segundos.")
        return (
            viz.tarjetas_resumen(rows, persona_sel, tipo_sel, desde, hasta, hoy),
            viz.gastos_en_tiempo(rows, persona_sel, tipo_sel, desde, hasta, hoy),
            viz.registrado_por_persona(rows, persona_sel, tipo_sel, desde, hasta, hoy),
            *cat_calcular(rows, persona_sel, tipo_sel, desde, hasta),
        )

    inputs = [persona, periodo, tipo]
    outputs = [tarjetas, plot_tiempo, plot_registrado, *cat_outputs]

    gr.on(
        triggers=[persona.change, periodo.change, tipo.change, refresh_button.click],
        fn=refrescar, inputs=inputs, outputs=outputs,
    )
    return refrescar, inputs, outputs
