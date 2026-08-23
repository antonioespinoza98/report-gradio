import gradio as gr
from datetime import date
from models import viajes
from transforms import viajes as viajes_transform

def _load_viajes():
    try:
        return viajes_transform.to_display_df(viajes.get_all())
    except Exception:
        return viajes_transform.to_display_df([])

def _parse_fecha(value, campo):
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{campo} debe tener formato YYYY-MM-DD")

def build_tab():
    """Build the 'Viajes' tab: create trips and list existing ones."""

    gr.Markdown(
        "### Viajes\n"
        "Los viajes son una etiqueta opcional para los gastos. No cambian la categoría del gasto."
    )

    with gr.Group():
        with gr.Row():
            nombre_input = gr.Textbox(
                label="Nombre",
                placeholder="Ej: Japón 2026"
            )
            destino_input = gr.Textbox(
                label="Destino (opcional)",
                placeholder="Ej: Tokio"
            )

        with gr.Row():
            inicio_input = gr.Textbox(
                label="Fecha inicio (YYYY-MM-DD)",
                value=date.today().isoformat()
            )
            fin_input = gr.Textbox(
                label="Fecha fin (YYYY-MM-DD)",
                value=date.today().isoformat()
            )

        crear_button = gr.Button("➕ Crear viaje", variant="primary")

    gr.Markdown("### Viajes registrados")
    viajes_table = gr.Dataframe(
        value=_load_viajes(),
        interactive=False,
        label="Viajes"
    )

    def on_crear_click(nombre, destino, inicio, fin):
        """Validate and persist a new trip."""
        try:
            if not (nombre or "").strip():
                raise ValueError("El nombre del viaje es obligatorio")

            d_inicio = _parse_fecha(inicio, "Fecha inicio")
            d_fin = _parse_fecha(fin, "Fecha fin")
            if d_fin < d_inicio:
                raise ValueError("La fecha de fin no puede ser anterior a la de inicio")

            viajes.insert({
                "nombre": nombre.strip(),
                "destino": (destino or "").strip(),
                "fecha_inicio": d_inicio,
                "fecha_fin": d_fin
            })

            hoy = date.today().isoformat()
            return "", "", hoy, hoy, _load_viajes()
        except Exception as e:
            raise gr.Error(f"Error al crear viaje: {e}")

    crear_button.click(
        fn=on_crear_click,
        inputs=[nombre_input, destino_input, inicio_input, fin_input],
        outputs=[nombre_input, destino_input, inicio_input, fin_input, viajes_table]
    )

    def refresh():
        """Reload the trips table when the tab is opened."""
        return _load_viajes()

    return refresh, viajes_table
