import gradio as gr
import plotly.graph_objects as go
from datetime import datetime, date
from models import gastos
from transforms import metricas

def build_tab():
    """Build the 'Métricas' tab: spending statistics by period grain."""

    gr.Markdown(
        "### Métricas de Gasto\n"
        "Sobre **gastos variables** únicamente — los gastos fijos no se incluyen.\n"
        "El promedio, la mediana y los extremos se calculan sólo sobre periodos "
        "completos; el periodo en curso se muestra aparte."
    )

    hoy = date.today()
    init_desde = date(hoy.year, 1, 1).isoformat()
    init_hasta = hoy.isoformat()

    with gr.Group():
        gr.Markdown("#### Filtros")
        with gr.Row():
            grano_input = gr.Radio(
                choices=list(metricas.GRANOS.keys()),
                value="Mensual",
                label="Periodo",
                interactive=True
            )

        with gr.Row():
            date_from_input = gr.Textbox(
                label="Desde (YYYY-MM-DD)",
                value=init_desde,
                interactive=True
            )
            date_to_input = gr.Textbox(
                label="Hasta (YYYY-MM-DD)",
                value=init_hasta,
                interactive=True
            )

    refresh_button = gr.Button("🔄 Actualizar métricas", variant="primary")

    def load_metricas(grano, date_from, date_to):
        """Compute summary, per-period table and chart for the current filters."""
        rows = gastos.get_filtered(
            persona=None,
            categoria=None,
            date_from=date_from,
            date_to=date_to
        )
        per = metricas.por_periodo(rows, grano)
        return (
            metricas.resumen(rows, grano),
            metricas.a_tabla(per),
            metricas.grafico(per, grano),
        )

    try:
        init_resumen, init_tabla, init_fig = load_metricas("Mensual", init_desde, init_hasta)
    except Exception:
        init_resumen = metricas.resumen([], "Mensual")
        init_tabla = metricas.a_tabla(metricas.por_periodo([], "Mensual"))
        init_fig = go.Figure()

    resumen_table = gr.Dataframe(
        value=init_resumen,
        interactive=False,
        label="Resumen"
    )

    plot = gr.Plot(value=init_fig, label="Gasto por periodo")

    periodos_table = gr.Dataframe(
        value=init_tabla,
        interactive=False,
        label="Detalle por periodo"
    )

    inputs = [grano_input, date_from_input, date_to_input]
    outputs = [resumen_table, periodos_table, plot]

    def load_all(grano, date_from, date_to):
        res, tabla, fig = load_metricas(grano, date_from, date_to)
        return res, tabla, fig

    refresh_button.click(fn=load_all, inputs=inputs, outputs=outputs)
    grano_input.change(fn=load_all, inputs=inputs, outputs=outputs)

    return load_all, inputs, outputs
