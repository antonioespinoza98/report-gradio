import gradio as gr
from models import gastos, viajes
from transforms import viajes_analisis as va


def _cargar():
    """Lee viajes y gastos; ante un fallo devuelve listas vacías."""
    try:
        return viajes.get_all(), gastos.get_all()
    except Exception:
        return [], []


def _vista(viaje_id, viajes_rows, gastos_rows):
    """Salidas del detalle de un viaje: titular, métricas, tabla y dos gráficos."""
    if not viaje_id:
        vacio = va.metricas_viaje([], [], 0)
        return (vacio[0], vacio[1], va.tabla_gastos([], 0),
                va.fig_categorias([], 0), va.fig_acumulado([], [], 0))
    titulo, met = va.metricas_viaje(gastos_rows, viajes_rows, viaje_id)
    return (titulo, met, va.tabla_gastos(gastos_rows, viaje_id),
            va.fig_categorias(gastos_rows, viaje_id),
            va.fig_acumulado(gastos_rows, viajes_rows, viaje_id))


def build_tab():
    """Pestaña 'Análisis de viajes': detalle por viaje y comparativa entre viajes."""
    viajes_rows, gastos_rows = _cargar()
    opciones = va.opciones_viajes(viajes_rows, gastos_rows)
    inicial = opciones[0][1] if opciones else None

    gr.Markdown(
        "### Análisis de viajes\n"
        "Solo gastos variables con viaje asignado. En viajes en curso, los días "
        "se cuentan hasta hoy."
    )

    with gr.Tabs():
        with gr.Tab("Detalle del viaje"):
            viaje_dd = gr.Dropdown(choices=opciones, value=inicial, label="Viaje", interactive=True)
            ini = _vista(inicial, viajes_rows, gastos_rows)
            titulo_md, met_df, tabla_df, cat_plot, acum_plot = _componentes_detalle(ini)

        with gr.Tab("Comparativa entre viajes"):
            comp_tabla_val, comp_fig_val = va.comparativa(gastos_rows, viajes_rows)
            comp_plot = gr.Plot(value=comp_fig_val, label="Costo por día")
            comp_tabla = gr.Dataframe(value=comp_tabla_val, interactive=False, label="Viajes")

    def al_cambiar(viaje_id):
        v, g = _cargar()
        return _vista(viaje_id, v, g)

    viaje_dd.change(fn=al_cambiar, inputs=[viaje_dd],
                    outputs=[titulo_md, met_df, tabla_df, cat_plot, acum_plot])

    def refrescar(viaje_id):
        """Relee la base y actualiza selector, detalle y comparativa."""
        v, g = _cargar()
        ops = va.opciones_viajes(v, g)
        validos = [o[1] for o in ops]
        sel = viaje_id if viaje_id in validos else (validos[0] if validos else None)
        comp_t, comp_f = va.comparativa(g, v)
        return (gr.update(choices=ops, value=sel), *_vista(sel, v, g), comp_f, comp_t)

    return refrescar, [viaje_dd], [viaje_dd, titulo_md, met_df, tabla_df,
                                   cat_plot, acum_plot, comp_plot, comp_tabla]


def _componentes_detalle(ini):
    """Crea los componentes del detalle con los valores iniciales ya calculados."""
    titulo_md = gr.Markdown(value=ini[0])
    met_df = gr.Dataframe(value=ini[1], interactive=False, label="Métricas del viaje")
    acum_plot = gr.Plot(value=ini[4], label="Gasto diario y acumulado")
    cat_plot = gr.Plot(value=ini[3], label="Gasto por categoría")
    tabla_df = gr.Dataframe(value=ini[2], interactive=False, label="Gastos del viaje")
    return titulo_md, met_df, tabla_df, cat_plot, acum_plot
