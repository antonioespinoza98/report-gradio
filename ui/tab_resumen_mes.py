import gradio as gr
import polars as pl
from datetime import datetime
from models import pagos_fijos, gastos_fijos, pagos_ahorros, ahorros, responsable_gastos
from transforms import tracker
from utils.constants import PERSONAS
from ui.aviso_saldo import aviso_limites_saldo

# Configuración de cada tracker: modelos, columnas y textos
_FIJOS = dict(
    pagos=pagos_fijos, items=gastos_fijos, id_col="gasto_fijo_id", name_col="gasto",
    verbo="Pagados", titulo="Tracking de Pagos de Gastos Fijos",
    label_cbg="{p}: marca lo que ya pagaste", msg="Pago",
)
_AHORROS = dict(
    pagos=pagos_ahorros, items=ahorros, id_col="ahorro_id", name_col="ahorro",
    verbo="Depositados", titulo="Tracking de Depósitos de Ahorro",
    label_cbg="{p}: marca lo que ya depositaste", msg="Depósito",
)


def _parse_mes_anio(mes, anio):
    return int(mes), int(anio)


def _estado(cfg, mes, anio):
    """Lee (y crea si faltan) los pagos del mes y arma el estado del tracker."""
    mes, anio = _parse_mes_anio(mes, anio)
    pagos_rows = cfg["pagos"].get_or_create_for_month(mes, anio)
    items_rows = cfg["items"].get_all()
    resp_rows = responsable_gastos.get_all()
    return tracker.estado_tracker(
        pagos_rows, items_rows, cfg["id_col"], cfg["name_col"], resp_rows, cfg["verbo"]
    )


def _vacio(cfg):
    col = cfg["name_col"].capitalize()
    return pl.DataFrame(schema={col: pl.Utf8, **{p: pl.Utf8 for p in PERSONAS}})


def build_tab():
    """Contenido de 'Resumen del Mes': trackers de gastos fijos y de ahorros.

    Cada tracker son dos CheckboxGroup (uno por persona) con guardado
    automático al marcar/desmarcar, más una tabla de solo lectura con ✅/⬜/N/A.
    Devuelve (fn_refresco, inputs, outputs) para conectarlo al select.
    """
    current_month = datetime.now().month
    current_year = datetime.now().year

    with gr.Group():
        with gr.Row():
            mes_input = gr.Dropdown(
                choices=[
                    ("Enero", 1), ("Febrero", 2), ("Marzo", 3),
                    ("Abril", 4), ("Mayo", 5), ("Junio", 6),
                    ("Julio", 7), ("Agosto", 8), ("Septiembre", 9),
                    ("Octubre", 10), ("Noviembre", 11), ("Diciembre", 12)
                ],
                value=current_month, label="Mes", interactive=True,
            )
            anio_input = gr.Number(value=current_year, label="Año", precision=0, interactive=True)

    def _seccion(cfg):
        """Crea los componentes de un tracker y registra sus eventos de guardado."""
        gr.Markdown(f"### {cfg['titulo']}")
        if cfg is _AHORROS:
            aviso_limites_saldo(abierto=False)
        try:
            est = _estado(cfg, current_month, current_year)
        except Exception:
            est = None

        cbgs = {}
        with gr.Row():
            for p in PERSONAS:
                cbgs[p] = gr.CheckboxGroup(
                    choices=est["choices"][p] if est else [],
                    value=est["pagados"][p] if est else [],
                    label=cfg["label_cbg"].format(p=p),
                    interactive=True,
                )
        progreso = gr.Markdown(est["progreso"] if est else "Sin datos disponibles.")
        tabla = gr.Dataframe(
            value=est["tabla"] if est else _vacio(cfg),
            interactive=False,
            label="Estado del mes (✅ hecho · ⬜ pendiente · N/A no corresponde)",
        )

        def on_input(seleccion, mes, anio, persona):
            """Guarda solo las diferencias de `persona` respecto a la base."""
            try:
                mes_i, anio_i = _parse_mes_anio(mes, anio)
                actual = _estado(cfg, mes_i, anio_i)
                sel = set(seleccion or [])
                previo = set(actual["pagados"][persona])
                cambios = [
                    (n, n in sel) for n in actual["choices"][persona]
                    if (n in sel) != (n in previo)
                ]
                for nombre, pagado in cambios:
                    res = cfg["pagos"].toggle_pago(actual["ids"][nombre], persona, mes_i, anio_i, pagado)
                    # Depósito marcado sin monto: no suma al saldo del fondo (solo ahorros lo devuelve)
                    if isinstance(res, dict) and res.get("aviso"):
                        gr.Warning(res["aviso"])
                nuevo = _estado(cfg, mes_i, anio_i) if cambios else actual
            except Exception as e:
                raise gr.Error(
                    f"No se pudo guardar el cambio ({e}). "
                    "Cambia de pestaña y vuelve para recargar el estado real."
                )
            if cambios:
                gr.Info(f"{cfg['msg']} guardado para {persona}: {len(cambios)} cambio(s).")
            return nuevo["progreso"], nuevo["tabla"]

        def _handler(persona):
            return lambda sel, mes, anio: on_input(sel, mes, anio, persona)

        for p in PERSONAS:
            cbgs[p].input(
                fn=_handler(p),
                inputs=[cbgs[p], mes_input, anio_input],
                outputs=[progreso, tabla],
                show_progress="hidden",
            )

        comps = [cbgs[p] for p in PERSONAS] + [progreso, tabla]
        return comps

    fijos_comps = _seccion(_FIJOS)
    ahorros_comps = _seccion(_AHORROS)

    def _updates(cfg, mes, anio):
        est = _estado(cfg, mes, anio)
        return (
            [gr.update(choices=est["choices"][p], value=est["pagados"][p]) for p in PERSONAS]
            + [est["progreso"], est["tabla"]]
        )

    def refrescar(mes, anio):
        """Relee ambos trackers para el mes/año elegido."""
        try:
            return tuple(_updates(_FIJOS, mes, anio) + _updates(_AHORROS, mes, anio))
        except Exception as e:
            gr.Warning(f"No se pudo cargar el resumen del mes: {e}")
            return tuple(gr.update() for _ in range(8))

    outputs = fijos_comps + ahorros_comps
    mes_input.change(fn=refrescar, inputs=[mes_input, anio_input], outputs=outputs)
    anio_input.change(fn=refrescar, inputs=[mes_input, anio_input], outputs=outputs)

    return refrescar, [mes_input, anio_input], outputs
