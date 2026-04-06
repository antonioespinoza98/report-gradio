import gradio as gr
from datetime import datetime, timedelta
from models import gastos, gastos_fijos, pagos_fijos, pagos_ahorros, responsable_gastos, ahorros
from transforms import visualizaciones
from utils.constants import PERSONAS, CATEGORIAS

def build_tab():
    """Build the 'Visualizaciones' tab with 6 chart types."""

    gr.Markdown("### Análisis de Gastos")

    current_month = datetime.now().month
    current_year = datetime.now().year

    # Filters for variable expense charts
    with gr.Group():
        gr.Markdown("#### Filtros — Gastos Variables")
        with gr.Row():
            persona_filter = gr.Dropdown(
                choices=PERSONAS + ["Ambos"],
                value="Ambos",
                label="Persona",
                interactive=True
            )
            categoria_filter = gr.Dropdown(
                choices=[None] + CATEGORIAS,
                value=None,
                label="Categoría (opcional)",
                interactive=True
            )

        with gr.Row():
            date_from_input = gr.Textbox(
                label="Desde (YYYY-MM-DD)",
                value=(datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
                interactive=True
            )
            date_to_input = gr.Textbox(
                label="Hasta (YYYY-MM-DD)",
                value=datetime.now().strftime("%Y-%m-%d"),
                interactive=True
            )

    # Filters for fixed expense charts
    with gr.Group():
        gr.Markdown("#### Filtros — Gastos Fijos")
        with gr.Row():
            mes_fijos = gr.Dropdown(
                choices=[
                    ("Enero", 1), ("Febrero", 2), ("Marzo", 3),
                    ("Abril", 4), ("Mayo", 5), ("Junio", 6),
                    ("Julio", 7), ("Agosto", 8), ("Septiembre", 9),
                    ("Octubre", 10), ("Noviembre", 11), ("Diciembre", 12)
                ],
                value=current_month,
                label="Mes (estado de pagos)",
                interactive=True
            )
            anio_fijos = gr.Number(
                value=current_year,
                label="Año (estado de pagos)",
                precision=0,
                interactive=True
            )

    refresh_button = gr.Button("🔄 Actualizar gráficas", variant="primary")

    def load_charts(persona, categoria, date_from, date_to, mes, anio):
        """Load all charts with current filters."""
        categoria = categoria if categoria else None
        mes = int(mes) if isinstance(mes, float) else mes
        anio = int(anio) if isinstance(anio, float) else anio

        gast_rows = gastos.get_filtered(
            persona=None,
            categoria=None,
            date_from=date_from,
            date_to=date_to
        )
        gf_rows = gastos_fijos.get_all()

        fig1 = visualizaciones.gastos_por_categoria(gast_rows, persona_filter=persona, date_from=date_from, date_to=date_to)
        fig2 = visualizaciones.gastos_en_tiempo(gast_rows, date_from=date_from, date_to=date_to)
        fig3 = visualizaciones.comparativa_personas(gast_rows, date_from=date_from, date_to=date_to)
        fig4 = visualizaciones.fijos_vs_variables(gf_rows, gast_rows)
        fig5 = visualizaciones.gastos_fijos_por_gasto(gf_rows)

        # Seed + fetch pagos for the selected month
        try:
            pagos_fijos.get_or_create_for_month(mes, anio)
            pf_rows = pagos_fijos.get_all()
            pf_rows = [r for r in pf_rows if r["mes"] == mes and r["anio"] == anio]
        except Exception:
            pf_rows = []
        try:
            resp_rows = responsable_gastos.get_all()
        except Exception:
            resp_rows = []
        fig6 = visualizaciones.estado_pagos_mes(pf_rows, gf_rows, resp_rows)

        # Estado de depósitos de ahorro
        try:
            pagos_ahorros.get_or_create_for_month(mes, anio)
            pa_rows = pagos_ahorros.get_all()
            pa_rows = [r for r in pa_rows if r["mes"] == mes and r["anio"] == anio]
        except Exception:
            pa_rows = []
        try:
            ah_rows = ahorros.get_all()
        except Exception:
            ah_rows = []
        fig7 = visualizaciones.estado_ahorros_mes(pa_rows, ah_rows, resp_rows)

        return fig1, fig2, fig3, fig4, fig5, fig6, fig7

    init_date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    init_date_to = datetime.now().strftime("%Y-%m-%d")

    try:
        fig1, fig2, fig3, fig4, fig5, fig6, fig7 = load_charts(
            "Ambos", None, init_date_from, init_date_to, current_month, current_year
        )
    except Exception:
        import plotly.graph_objects as go
        fig1 = fig2 = fig3 = fig4 = fig5 = fig6 = fig7 = go.Figure()

    with gr.Row():
        plot1 = gr.Plot(value=fig1, label="Gastos por Categoría")
        plot2 = gr.Plot(value=fig2, label="Gastos en el Tiempo")

    with gr.Row():
        plot3 = gr.Plot(value=fig3, label="Comparativa Marco vs Chiara")
        plot4 = gr.Plot(value=fig4, label="Gastos Fijos vs Variables")

    with gr.Row():
        plot5 = gr.Plot(value=fig5, label="Gastos Fijos por Concepto")
        plot6 = gr.Plot(value=fig6, label="Estado de Pagos del Mes")

    with gr.Row():
        plot7 = gr.Plot(value=fig7, label="Estado de Depósitos de Ahorro del Mes")

    # ── Tipo de Gasto por Categoría ─────────────────────────────────────────────
    gr.Markdown("---\n#### Tipo de Gasto por Categoría")
    with gr.Row():
        tipo_persona_filter = gr.Dropdown(
            choices=PERSONAS + ["Ambos"],
            value="Ambos",
            label="Persona",
            interactive=True
        )

    def load_tipo_chart(persona, date_from, date_to):
        gast_rows = gastos.get_filtered(persona=None, categoria=None, date_from=date_from, date_to=date_to)
        return visualizaciones.tipo_gasto_por_categoria(gast_rows, persona_filter=persona, date_from=date_from, date_to=date_to)

    try:
        fig8 = load_tipo_chart("Ambos", init_date_from, init_date_to)
    except Exception:
        import plotly.graph_objects as go
        fig8 = go.Figure()

    plot8 = gr.Plot(value=fig8, label="Tipo de Gasto por Categoría")

    tipo_inputs = [tipo_persona_filter, date_from_input, date_to_input]

    # ── Wire events ─────────────────────────────────────────────────────────────

    all_inputs = [persona_filter, categoria_filter, date_from_input, date_to_input, mes_fijos, anio_fijos]
    all_outputs = [plot1, plot2, plot3, plot4, plot5, plot6, plot7]

    refresh_button.click(fn=load_charts, inputs=all_inputs, outputs=all_outputs)
    refresh_button.click(fn=load_tipo_chart, inputs=tipo_inputs, outputs=[plot8])
    persona_filter.change(fn=load_charts, inputs=all_inputs, outputs=all_outputs)
    mes_fijos.change(fn=load_charts, inputs=all_inputs, outputs=all_outputs)
    anio_fijos.change(fn=load_charts, inputs=all_inputs, outputs=all_outputs)
    tipo_persona_filter.change(fn=load_tipo_chart, inputs=tipo_inputs, outputs=[plot8])

    def load_all(persona, categoria, date_from, date_to, mes, anio):
        charts = load_charts(persona, categoria, date_from, date_to, mes, anio)
        tipo = load_tipo_chart("Ambos", date_from, date_to)
        return (*charts, tipo)

    return load_all, all_inputs, [*all_outputs, plot8]
