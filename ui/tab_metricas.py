import gradio as gr
from datetime import date, timedelta
from models import gastos
from transforms import metricas
from utils.constants import PERSONAS, TIPO_GASTO_OPTIONS

TODAS = "Todas"
TODOS = "Todos"


def build_tab():
    """Construye la pestaña 'Métricas': tarjetas, gráfico y estadísticas por periodo."""

    gr.Markdown(
        "### Métricas de Gasto\n"
        "Sobre **gastos variables** únicamente: los gastos fijos no se incluyen.\n\n"
        "- El promedio, la mediana y los extremos se calculan solo sobre periodos "
        "**completos**; con menos de 3 se muestra *datos insuficientes*. Cuando media y "
        "mediana difieren más de 20 %, se prefiere la mediana.\n"
        "- **El periodo en curso se excluye** de promedios y de la variación (no es "
        "comparable con uno terminado) y se dibuja aparte, en gris.\n"
        "- La **variación** compara cada periodo completo con el inmediato anterior; "
        "muestra «—» si el anterior fue 0 €.\n"
        "- *Agrupar por* solo cambia el detalle por periodo y el gráfico; el total y el "
        "Nº de gastos dependen del rango *Desde/Hasta* y de los filtros."
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
                label="Agrupar por (cambia el detalle por periodo, no el total del rango)",
                interactive=True,
            )
        with gr.Row():
            persona_input = gr.Dropdown(
                choices=[TODAS] + PERSONAS, value=TODAS, label="Persona", interactive=True
            )
            tipo_input = gr.Dropdown(
                choices=[TODOS] + TIPO_GASTO_OPTIONS, value=TODOS,
                label="Tipo de gasto", interactive=True,
            )
        with gr.Row():
            date_from_input = gr.Textbox(
                label="Desde (AAAA-MM-DD, vacío = sin límite)", value=init_desde, interactive=True
            )
            date_to_input = gr.Textbox(
                label="Hasta (AAAA-MM-DD, vacío = sin límite)", value=init_hasta, interactive=True
            )
        with gr.Row():
            btn_mes = gr.Button("Este mes", size="sm")
            btn_30 = gr.Button("Últimos 30 días", size="sm")
            btn_anio = gr.Button("Este año", size="sm")
            btn_todo = gr.Button("Todo", size="sm")

    refresh_button = gr.Button("🔄 Actualizar métricas", variant="primary")

    def load_metricas(grano, persona, tipo, date_from, date_to):
        """Calcula tarjetas, estadísticas, atípicos, detalle y gráfico para los filtros."""
        for valor in (date_from, date_to):
            if valor and valor.strip():
                try:
                    date.fromisoformat(valor.strip())
                except ValueError:
                    raise gr.Error("Fechas inválidas: usá el formato AAAA-MM-DD.")
        date_from = (date_from or "").strip() or None
        date_to = (date_to or "").strip() or None
        if date_from and date_to and date_from > date_to:
            raise gr.Error("«Desde» no puede ser posterior a «Hasta».")
        rows = gastos.get_filtered(
            persona=None if persona in (None, "", TODAS) else persona,
            categoria=None,
            date_from=date_from,
            date_to=date_to,
        )
        tipo = None if tipo in (None, "", TODOS) else tipo
        return metricas.construir(rows, grano, tipo)

    try:
        inicial = load_metricas("Mensual", TODAS, TODOS, init_desde, init_hasta)
    except Exception:
        inicial = metricas.construir([], "Mensual")
    init_cards, init_resumen, init_atip, init_tabla, init_fig = inicial

    cards = gr.HTML(value=init_cards)
    plot = gr.Plot(value=init_fig, label="Gasto por periodo")
    resumen_table = gr.Dataframe(
        value=init_resumen, interactive=False, label="Estadísticas por periodo (con n)"
    )
    atipicos_table = gr.Dataframe(
        value=init_atip, interactive=False,
        label="Gastos atípicos: los 15 mayores fuera de 1,5·IQR (se marcan, no se descartan)",
    )
    periodos_table = gr.Dataframe(
        value=init_tabla, interactive=False, label="Detalle por periodo"
    )

    inputs = [grano_input, persona_input, tipo_input, date_from_input, date_to_input]
    outputs = [cards, resumen_table, atipicos_table, periodos_table, plot]

    def load_all(grano, persona, tipo, date_from, date_to):
        c, res, atip, tabla, fig = load_metricas(grano, persona, tipo, date_from, date_to)
        return c, res, atip, tabla, fig

    # Atajos: rellenan Desde/Hasta y recalculan.
    def rango_mes():
        h = date.today()
        return date(h.year, h.month, 1).isoformat(), h.isoformat()

    def rango_30():
        h = date.today()
        return (h - timedelta(days=29)).isoformat(), h.isoformat()

    def rango_anio():
        h = date.today()
        return date(h.year, 1, 1).isoformat(), h.isoformat()

    def rango_todo():
        return "", ""

    for boton, fn in ((btn_mes, rango_mes), (btn_30, rango_30),
                      (btn_anio, rango_anio), (btn_todo, rango_todo)):
        boton.click(fn=fn, inputs=[], outputs=[date_from_input, date_to_input]).then(
            fn=load_all, inputs=inputs, outputs=outputs
        )

    refresh_button.click(fn=load_all, inputs=inputs, outputs=outputs)
    for control in (grano_input, persona_input, tipo_input):
        control.change(fn=load_all, inputs=inputs, outputs=outputs)
    # Las fechas también aplican al pulsar Enter, sin depender del botón.
    date_from_input.submit(fn=load_all, inputs=inputs, outputs=outputs)
    date_to_input.submit(fn=load_all, inputs=inputs, outputs=outputs)

    return load_all, inputs, outputs
