import gradio as gr
import plotly.graph_objects as go
from datetime import datetime, timedelta
from models import gastos
from transforms import visualizaciones
from utils.constants import TIPO_GASTO_OPTIONS

def _default_dates():
    return (
        (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
        datetime.now().strftime("%Y-%m-%d"),
    )

def build_tab():
    """Build the 'Visualizaciones - por categoría' tab."""

    gr.Markdown("### Gastos por Categoría")

    init_date_from, init_date_to = _default_dates()

    with gr.Group():
        gr.Markdown("#### Filtros")
        with gr.Row():
            tipo_filter = gr.Dropdown(
                choices=TIPO_GASTO_OPTIONS,
                value=TIPO_GASTO_OPTIONS[0],
                label="Tipo de Gasto",
                interactive=True
            )

        with gr.Row():
            date_from_input = gr.Textbox(
                label="Desde (YYYY-MM-DD)",
                value=init_date_from,
                interactive=True
            )
            date_to_input = gr.Textbox(
                label="Hasta (YYYY-MM-DD)",
                value=init_date_to,
                interactive=True
            )

    refresh_button = gr.Button("🔄 Actualizar gráfica", variant="primary")

    def load_chart(tipo, date_from, date_to):
        """Load the category chart for the selected tipo de gasto."""
        gast_rows = gastos.get_filtered(
            persona=None,
            categoria=None,
            date_from=date_from,
            date_to=date_to
        )
        return visualizaciones.tipo_gasto_por_categoria(
            gast_rows, tipo_filter=tipo, date_from=date_from, date_to=date_to
        )

    try:
        fig = load_chart(TIPO_GASTO_OPTIONS[0], init_date_from, init_date_to)
    except Exception:
        fig = go.Figure()

    plot = gr.Plot(value=fig, label="Tipo de Gasto por Categoría")

    inputs = [tipo_filter, date_from_input, date_to_input]
    outputs = [plot]

    refresh_button.click(fn=load_chart, inputs=inputs, outputs=outputs)
    tipo_filter.change(fn=load_chart, inputs=inputs, outputs=outputs)

    return load_chart, inputs, outputs
