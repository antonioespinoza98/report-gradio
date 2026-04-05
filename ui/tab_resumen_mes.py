import gradio as gr
import polars as pl
from datetime import datetime
from models import pagos_fijos, gastos_fijos
from utils.constants import PERSONAS

def build_tab():
    """Build the 'Resumen del Mes' tab with month selector and payment tracker."""

    gr.Markdown("### Tracking de Pagos de Gastos Fijos")

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
                value=current_month,
                label="Mes",
                interactive=True
            )
            anio_input = gr.Number(
                value=current_year,
                label="Año",
                precision=0,
                interactive=True
            )

    def load_month_data(mes, anio):
        """Load payment data for a given month."""
        mes = int(mes) if isinstance(mes, float) else mes
        anio = int(anio) if isinstance(anio, float) else anio

        # Seed pagos_fijos if needed
        pagos_fijos.get_or_create_for_month(mes, anio)

        # Fetch payment records
        pagos_rows = pagos_fijos.get_all()
        pagos_df = pl.DataFrame(pagos_rows) if pagos_rows else pl.DataFrame()

        # Filter to current month/year
        if not pagos_df.is_empty():
            pagos_df = pagos_df.filter(
                (pl.col("mes") == mes) & (pl.col("anio") == anio)
            )

        # Fetch gastos_fijos to get gasto names
        gf_rows = gastos_fijos.get_all()
        gf_df = pl.DataFrame(gf_rows) if gf_rows else pl.DataFrame()

        # Join to get gasto names
        if not pagos_df.is_empty() and not gf_df.is_empty():
            pagos_df = pagos_df.join(gf_df, left_on="gasto_fijo_id", right_on="id")
            pagos_df = pagos_df.select(["gasto", "persona", "pagado"])

        # Pivot: rows = gastos, columns = personas (Marco, Chiara)
        if not pagos_df.is_empty():
            pivot_data = []
            for gasto in pagos_df["gasto"].unique():
                gasto_rows = pagos_df.filter(pl.col("gasto") == gasto)
                row_data = {"Gasto": gasto}
                for persona in PERSONAS:
                    persona_row = gasto_rows.filter(pl.col("persona") == persona)
                    if not persona_row.is_empty():
                        row_data[persona] = bool(persona_row["pagado"][0])
                    else:
                        row_data[persona] = False
                pivot_data.append(row_data)
            pivot_df = pl.DataFrame(pivot_data)
        else:
            pivot_df = pl.DataFrame(schema={"Gasto": pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})

        return pivot_df

    try:
        initial_data = load_month_data(current_month, current_year)
    except Exception:
        initial_data = pl.DataFrame(schema={"Gasto": pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})
    payment_table = gr.Dataframe(
        value=initial_data,
        interactive=True,
        label="Estado de pagos"
    )

    def on_month_change(mes, anio):
        """Reload data when month changes."""
        return load_month_data(mes, anio)

    def on_payment_edit(updated_df, mes, anio):
        """Handle checkbox changes in the payment table."""
        if updated_df is None:
            return load_month_data(mes, anio)

        # Gradio may pass a pandas DataFrame — convert to Polars
        if not isinstance(updated_df, pl.DataFrame):
            updated_df = pl.from_pandas(updated_df)

        if updated_df.is_empty():
            return load_month_data(mes, anio)

        try:
            mes = int(mes) if isinstance(mes, float) else mes
            anio = int(anio) if isinstance(anio, float) else anio

            # Convert DataFrame to rows
            updated_rows = updated_df.to_dicts()

            # Get all gastos_fijos for mapping gasto -> gasto_fijo_id
            gf_rows = gastos_fijos.get_all()
            gf_map = {row["gasto"]: row["id"] for row in gf_rows}

            # Update each changed cell
            for row in updated_rows:
                gasto = row["Gasto"]
                gasto_fijo_id = gf_map.get(gasto)
                if gasto_fijo_id:
                    for persona in PERSONAS:
                        pagado = row.get(persona, False)
                        pagos_fijos.toggle_pago(gasto_fijo_id, persona, mes, anio, pagado)

            return load_month_data(mes, anio)
        except Exception as e:
            gr.Error(f"Error al actualizar: {str(e)}")
            return load_month_data(mes, anio)

    # Wire month selector
    mes_input.change(
        fn=on_month_change,
        inputs=[mes_input, anio_input],
        outputs=[payment_table]
    )
    anio_input.change(
        fn=on_month_change,
        inputs=[mes_input, anio_input],
        outputs=[payment_table]
    )

    # Wire payment table edits
    payment_table.change(
        fn=on_payment_edit,
        inputs=[payment_table, mes_input, anio_input],
        outputs=[payment_table]
    )
