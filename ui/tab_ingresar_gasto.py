import logging
import gradio as gr
from datetime import datetime, date
from models import ahorros, fondos, gastos, viajes, presupuestos
from transforms import gastos as gastos_transform
from transforms import fondos as fondos_transform
from transforms import presupuestos as presupuestos_transform
from transforms import viajes as viajes_transform
from utils.constants import PERSONAS, CATEGORIAS, TIPO_GASTO_OPTIONS

logger = logging.getLogger(__name__)

def _parse_fecha(fecha):
    """Parse a YYYY-MM-DD string; return None if incomplete or invalid."""
    try:
        return date.fromisoformat(str(fecha).strip())
    except (TypeError, ValueError):
        return None

def _viaje_para_fecha(fecha):
    """Trip id whose range contains fecha, or NINGUNO."""
    d = _parse_fecha(fecha)
    if d is None:
        return viajes_transform.NINGUNO
    try:
        match = viajes.find_by_fecha(d)
    except Exception:
        return viajes_transform.NINGUNO
    return match["id"] if match else viajes_transform.NINGUNO

def _avisar_presupuesto(categoria, fecha):
    """Muestra el estado del presupuesto de la categoría tras guardar un gasto.

    Es solo un aviso: cualquier fallo se registra en el log y nunca afecta al guardado.
    """
    try:
        d = _parse_fecha(fecha) or date.today()
        filas = presupuestos.get_consumo_mes(d.month, d.year)
        for mensaje, nivel in presupuestos_transform.avisos_categoria(filas, categoria):
            (gr.Warning if nivel == "warning" else gr.Info)(mensaje)
    except Exception:
        logger.exception("No se pudo leer el presupuesto de la categoría «%s»", categoria)

def _avisar_fondo(guardado):
    """Muestra el saldo del fondo (y el exceso, si lo hay) tras guardar un gasto pagado con fondo.

    El saldo leído ya incluye el gasto recién guardado, por eso no se resta de nuevo.
    Es solo un aviso: cualquier fallo se registra en el log y nunca afecta al guardado.
    """
    try:
        fondo = next((f for f in fondos.get_saldos() if f["id"] == guardado["fondo_id"]), None)
        for mensaje, nivel in fondos_transform.avisos_retiro(
                fondo, guardado["monto"], guardado["pagado_por"]):
            (gr.Warning if nivel == "warning" else gr.Info)(mensaje)
    except Exception:
        logger.exception("No se pudo leer el saldo del fondo %s", guardado.get("fondo_id"))

def _fondo_choices():
    """«Ninguno» + un fondo por cada ahorro; si no se puede leer, solo «Ninguno»."""
    try:
        filas = [(r["ahorro"], r["id"]) for r in ahorros.get_all()]
    except Exception:
        logger.exception("No se pudieron leer los ahorros para «Pagado con fondo»")
        filas = []
    return [(fondos_transform.NINGUNO_LABEL, fondos_transform.NINGUNO)] + filas

def _viaje_choices():
    try:
        return viajes_transform.to_choices(viajes.get_all())
    except Exception:
        return viajes_transform.to_choices([])

def build_tab():
    """Build the 'Ingresar Gasto' tab UI."""

    gr.Markdown("### Registrar nuevo gasto")

    hoy = datetime.now().strftime("%Y-%m-%d")

    with gr.Group():
        with gr.Row():
            persona_input = gr.Dropdown(
                choices=PERSONAS,
                label="Persona",
                value=PERSONAS[0]
            )
            categoria_input = gr.Dropdown(
                choices=CATEGORIAS,
                label="Categoría",
                value=CATEGORIAS[0]
            )
            tipo_input = gr.Dropdown(
                choices=TIPO_GASTO_OPTIONS,
                label="Tipo de Gasto",
                value=TIPO_GASTO_OPTIONS[0]
            )

        with gr.Row():
            descripcion_input = gr.Textbox(
                label="Descripción",
                placeholder="Ej: Compra en supermercado"
            )
            monto_input = gr.Number(
                label="Monto",
                value=0,
                precision=2
            )

        with gr.Row():
            fecha_input = gr.Textbox(
                label="Fecha (YYYY-MM-DD)",
                value=hoy
            )
            viaje_input = gr.Dropdown(
                choices=_viaje_choices(),
                label="Viaje (opcional)",
                value=_viaje_para_fecha(hoy),
                info="Se preselecciona si la fecha cae dentro de un viaje. Podés cambiarlo o dejarlo en ninguno."
            )

        with gr.Row():
            fondo_input = gr.Dropdown(
                choices=_fondo_choices(),
                label="Pagado con fondo (opcional)",
                value=fondos_transform.NINGUNO,
                info="Si el gasto salió de un fondo de ahorro: no cuenta como gasto de caja ni consume presupuestos."
            )
            pagado_input = gr.Dropdown(
                choices=PERSONAS,
                label="Quién pagó",
                value=PERSONAS[0],
                info="Por defecto, quien registra. Cambialo si pagó la otra persona."
            )

        def on_persona_change(persona):
            """El pagador por defecto sigue a la persona que registra."""
            return gr.update(value=persona)

        def on_fecha_change(fecha):
            """Pre-select the trip covering the entered date (does not lock it in)."""
            return gr.update(value=_viaje_para_fecha(fecha))

        def on_save_click(persona, descripcion, categoria, tipo, monto, fecha, viaje_id, fondo_id, pagado_por):
            """Handle save button click."""
            try:
                guardado = gastos.insert({
                    "persona": persona,
                    "descripcion": descripcion,
                    "categoria": categoria,
                    "tipo_de_gasto": tipo,
                    "monto": monto,
                    "fecha": fecha,
                    "viaje_id": viaje_id if viaje_id else None,
                    "fondo_id": fondo_id if fondo_id else None,
                    "pagado_por": pagado_por
                })

                # Los gastos personales no consumen presupuesto: no hay nada que avisar.
                if tipo == "Gasto Común":
                    _avisar_presupuesto(categoria, fecha)
                if guardado.get("fondo_id"):
                    _avisar_fondo(guardado)

                # Fetch last 10 and update table
                recent = gastos.get_last_n(10)
                df = gastos_transform.to_display_df(recent)

                nueva_fecha = datetime.now().strftime("%Y-%m-%d")

                return (
                    "",  # Clear descripcion
                    0,   # Clear monto
                    nueva_fecha,  # Reset fecha
                    gr.update(choices=_viaje_choices(), value=_viaje_para_fecha(nueva_fecha)),  # Reset viaje
                    fondos_transform.NINGUNO,  # Reset fondo: evita retiros repetidos sin querer
                    persona,  # Reset quién pagó (= persona)
                    df   # Update table
                )
            except Exception as e:
                raise gr.Error(f"Error al guardar: {str(e)}")

        save_button = gr.Button("💾 Guardar gasto", variant="primary")

    # Display last 10 expenses
    gr.Markdown("### Últimos 10 gastos")
    try:
        recent = gastos.get_last_n(10)
        initial_df = gastos_transform.to_display_df(recent)
    except Exception:
        initial_df = gastos_transform.to_display_df([])

    gastos_table = gr.Dataframe(
        value=initial_df,
        interactive=False,
        label="Gastos registrados"
    )

    # Pre-select the trip whenever the date changes
    fecha_input.change(
        fn=on_fecha_change,
        inputs=[fecha_input],
        outputs=[viaje_input]
    )

    # El pagador por defecto sigue a la persona que registra
    persona_input.change(fn=on_persona_change, inputs=[persona_input], outputs=[pagado_input])

    # Wire save button
    save_button.click(
        fn=on_save_click,
        inputs=[persona_input, descripcion_input, categoria_input, tipo_input, monto_input, fecha_input, viaje_input,
                fondo_input, pagado_input],
        outputs=[descripcion_input, monto_input, fecha_input, viaje_input, fondo_input, pagado_input, gastos_table]
    )

    def refrescar(fondo_actual):
        """Relee viajes y fondos para que aparezcan los creados en otras pestañas."""
        choices = _fondo_choices()
        ids = {v for _, v in choices}
        valor = fondo_actual if fondo_actual in ids else fondos_transform.NINGUNO
        return gr.update(choices=_viaje_choices()), gr.update(choices=choices, value=valor)

    return refrescar, [fondo_input], [viaje_input, fondo_input]
