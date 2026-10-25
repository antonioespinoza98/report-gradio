import gradio as gr

from transforms.fondos import AVISO_SALDO_TEXTO, AVISO_SALDO_TITULO


def aviso_limites_saldo(abierto: bool = False) -> gr.Accordion:
    """Acordeón con los límites del cálculo del saldo de un fondo (definido una sola vez).

    Se muestra en el Panel de Control, en Gastos Fijos > Ahorros y en Resumen del Mes.
    `abierto=True` lo deja desplegado; el título (con ⚠️) siempre es visible.
    """
    with gr.Accordion(AVISO_SALDO_TITULO, open=abierto) as acc:
        gr.Markdown(AVISO_SALDO_TEXTO)
    return acc
