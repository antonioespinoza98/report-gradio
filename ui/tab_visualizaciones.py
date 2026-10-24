import gradio as gr
from datetime import datetime, timedelta
from models import gastos
from transforms import visualizaciones
from utils.constants import PERSONAS

def build_tab():
    """Build the 'Visualizaciones' tab (gastos en el tiempo y comparativa de personas)."""

    gr.Markdown("### Análisis de Gastos")

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

    refresh_button = gr.Button("🔄 Actualizar gráficas", variant="primary")

    def load_charts(persona, date_from, date_to):
        """Load all charts with current filters."""
        gast_rows = gastos.get_filtered(
            persona=None,
            categoria=None,
            date_from=date_from,
            date_to=date_to
        )

        fig2 = visualizaciones.gastos_en_tiempo(gast_rows, date_from=date_from, date_to=date_to)
        fig3 = visualizaciones.comparativa_personas(gast_rows, date_from=date_from, date_to=date_to)
        return fig2, fig3

    init_date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    init_date_to = datetime.now().strftime("%Y-%m-%d")

    try:
        fig2, fig3 = load_charts("Ambos", init_date_from, init_date_to)
    except Exception:
        import plotly.graph_objects as go
        fig2 = fig3 = go.Figure()

    with gr.Row():
        plot2 = gr.Plot(value=fig2, label="Gastos en el Tiempo")

    with gr.Row():
        plot3 = gr.Plot(value=fig3, label="Comparativa de Gastos Variables")

    # ── Wire events ─────────────────────────────────────────────────────────────

    all_inputs = [persona_filter, date_from_input, date_to_input]
    all_outputs = [plot2, plot3]

    refresh_button.click(fn=load_charts, inputs=all_inputs, outputs=all_outputs)
    persona_filter.change(fn=load_charts, inputs=all_inputs, outputs=all_outputs)

    return load_charts, all_inputs, all_outputs
