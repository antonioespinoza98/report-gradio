import gradio as gr
from datetime import datetime, date
from models import gastos, viajes
from transforms import gastos as gastos_transform
from transforms import viajes as viajes_transform
from utils.constants import PERSONAS, CATEGORIAS, TIPO_GASTO_OPTIONS

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

        def on_fecha_change(fecha):
            """Pre-select the trip covering the entered date (does not lock it in)."""
            return gr.update(value=_viaje_para_fecha(fecha))

        def on_save_click(persona, descripcion, categoria, tipo, monto, fecha, viaje_id):
            """Handle save button click."""
            try:
                gastos.insert({
                    "persona": persona,
                    "descripcion": descripcion,
                    "categoria": categoria,
                    "tipo_de_gasto": tipo,
                    "monto": monto,
                    "fecha": fecha,
                    "viaje_id": viaje_id if viaje_id else None
                })

                # Fetch last 10 and update table
                recent = gastos.get_last_n(10)
                df = gastos_transform.to_display_df(recent)

                nueva_fecha = datetime.now().strftime("%Y-%m-%d")

                return (
                    "",  # Clear descripcion
                    0,   # Clear monto
                    nueva_fecha,  # Reset fecha
                    gr.update(choices=_viaje_choices(), value=_viaje_para_fecha(nueva_fecha)),  # Reset viaje
                    df   # Update table
                )
            except Exception as e:
                gr.Error(f"Error al guardar: {str(e)}")
                return None, None, None, None, None

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

    # Wire save button
    save_button.click(
        fn=on_save_click,
        inputs=[persona_input, descripcion_input, categoria_input, tipo_input, monto_input, fecha_input, viaje_input],
        outputs=[descripcion_input, monto_input, fecha_input, viaje_input, gastos_table]
    )

    def refresh_viajes():
        """Re-read trips so ones created in the Viajes tab show up here."""
        return gr.update(choices=_viaje_choices())

    return refresh_viajes, viaje_input
