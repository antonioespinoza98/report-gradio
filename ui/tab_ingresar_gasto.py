import gradio as gr
from datetime import datetime
from models import gastos
from transforms import gastos as gastos_transform
from utils.constants import PERSONAS, CATEGORIAS

def build_tab():
    """Build the 'Ingresar Gasto' tab UI."""

    gr.Markdown("### Registrar nuevo gasto")

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

        fecha_input = gr.Textbox(
            label="Fecha (YYYY-MM-DD)",
            value=datetime.now().strftime("%Y-%m-%d")
        )

        def on_save_click(persona, descripcion, categoria, monto, fecha):
            """Handle save button click."""
            try:
                gastos.insert({
                    "persona": persona,
                    "descripcion": descripcion,
                    "categoria": categoria,
                    "monto": monto,
                    "fecha": fecha
                })

                # Fetch last 10 and update table
                recent = gastos.get_last_n(10)
                df = gastos_transform.to_display_df(recent)

                return (
                    "",  # Clear descripcion
                    0,   # Clear monto
                    datetime.now().strftime("%Y-%m-%d"),  # Reset fecha
                    df   # Update table
                )
            except Exception as e:
                gr.Error(f"Error al guardar: {str(e)}")
                return None, None, None, None

        save_button = gr.Button("💾 Guardar gasto", variant="primary")

    # Display last 10 expenses
    gr.Markdown("### Últimos 10 gastos")
    recent = gastos.get_last_n(10)
    initial_df = gastos_transform.to_display_df(recent)

    gastos_table = gr.Dataframe(
        value=initial_df,
        interactive=False,
        label="Gastos registrados"
    )

    # Wire save button
    save_button.click(
        fn=on_save_click,
        inputs=[persona_input, descripcion_input, categoria_input, monto_input, fecha_input],
        outputs=[descripcion_input, monto_input, fecha_input, gastos_table]
    )
