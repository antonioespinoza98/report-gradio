import gradio as gr
from datetime import datetime, timedelta
from models import gastos, gastos_fijos
from transforms import visualizaciones
from utils.constants import PERSONAS, CATEGORIAS

def build_tab():
    """Build the 'Visualizaciones' tab with 4 chart types."""

    gr.Markdown("### Análisis de Gastos")

    # Shared filters
    with gr.Group():
        gr.Markdown("#### Filtros")
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

        refresh_button = gr.Button("🔄 Actualizar gráficas", variant="primary")

    def load_charts(persona, categoria, date_from, date_to):
        """Load all charts with current filters."""
        # Convert None strings to actual None
        categoria = categoria if categoria else None

        # Fetch all gastos for this period
        gast_rows = gastos.get_filtered(
            persona=None,  # Fetch all, filter in transforms
            categoria=None,
            date_from=date_from,
            date_to=date_to
        )

        # Chart 1: Gastos por categoría
        fig1 = visualizaciones.gastos_por_categoria(
            gast_rows,
            persona_filter=persona,
            date_from=date_from,
            date_to=date_to
        )

        # Chart 2: Gastos en el tiempo
        fig2 = visualizaciones.gastos_en_tiempo(
            gast_rows,
            date_from=date_from,
            date_to=date_to
        )

        # Chart 3: Comparativa personas
        fig3 = visualizaciones.comparativa_personas(
            gast_rows,
            date_from=date_from,
            date_to=date_to
        )

        # Chart 4: Fijos vs Variables
        gf_rows = gastos_fijos.get_all()
        fig4 = visualizaciones.fijos_vs_variables(gf_rows, gast_rows)

        return fig1, fig2, fig3, fig4

    # Load initial charts
    init_date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    init_date_to = datetime.now().strftime("%Y-%m-%d")

    fig1, fig2, fig3, fig4 = load_charts("Ambos", None, init_date_from, init_date_to)

    # Charts
    with gr.Row():
        plot1 = gr.Plot(value=fig1, label="Gastos por Categoría")
        plot2 = gr.Plot(value=fig2, label="Gastos en el Tiempo")

    with gr.Row():
        plot3 = gr.Plot(value=fig3, label="Comparativa Marco vs Chiara")
        plot4 = gr.Plot(value=fig4, label="Gastos Fijos vs Variables")

    # Wire refresh button
    refresh_button.click(
        fn=load_charts,
        inputs=[persona_filter, categoria_filter, date_from_input, date_to_input],
        outputs=[plot1, plot2, plot3, plot4]
    )

    # Also update on filter change
    persona_filter.change(
        fn=load_charts,
        inputs=[persona_filter, categoria_filter, date_from_input, date_to_input],
        outputs=[plot1, plot2, plot3, plot4]
    )
