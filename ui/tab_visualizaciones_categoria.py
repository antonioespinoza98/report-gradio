import gradio as gr
from transforms import visualizaciones


def build_tab():
    """Contenido del sub-tab 'Visualizaciones - por categoría'.

    No tiene filtros propios: usa los compartidos de la pestaña (persona, periodo, tipo).
    Devuelve (componentes_de_salida, calcular), donde
    calcular(rows, persona, tipo, desde, hasta) -> tupla de valores para esos componentes.
    """
    gr.Markdown("### Gastos por categoría")
    gr.Markdown(f"*{visualizaciones.NOTA_REGISTRADO}*")
    aviso = gr.Markdown("")
    plot_cat = gr.Plot(value=visualizaciones.figura_inicial(), label="Gasto por categoría")
    plot_mezcla = gr.Plot(value=visualizaciones.figura_inicial(),
                          label="Mezcla de categorías: Marco vs Chiara")

    def calcular(rows, persona, tipo, desde, hasta):
        return (
            visualizaciones.aviso_categorias(rows, persona, tipo, desde, hasta),
            visualizaciones.gasto_por_categoria(rows, persona, tipo, desde, hasta),
            visualizaciones.mezcla_categorias(rows, persona, tipo, desde, hasta),
        )

    return [aviso, plot_cat, plot_mezcla], calcular
