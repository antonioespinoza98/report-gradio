import gradio as gr
import polars as pl
from models import gastos_fijos, ingresos, ahorros, responsable_gastos, gastos
from transforms import gastos as gastos_transform, resumen as resumen_transform
from utils.constants import PERSONAS, RESPONSABLE_OPTIONS

def build_tab():
    """Build the 'Tablas Predeterminadas' tab with 5 sub-tabs."""

    with gr.Tabs(id="tablas_tabs"):

            # Sub-tab 1: Gastos Fijos
            with gr.Tab(label="Gastos Fijos", id="gastos_fijos_tab"):
                gr.Markdown("### Gestión de Gastos Fijos")

                gastos_fijos_state = gr.State(value=[])

                def load_gastos_fijos():
                    rows = gastos_fijos.get_all()
                    gastos_fijos_state.value = rows
                    df = pl.DataFrame(rows) if rows else pl.DataFrame({"id": [], "gasto": [], "total": []})
                    return df

                initial_gf = load_gastos_fijos()
                gf_table = gr.Dataframe(
                    value=initial_gf,
                    interactive=True,
                    label="Gastos Fijos"
                )

                def save_gastos_fijos_changes(new_df):
                    """Diff and save changes to gastos_fijos."""
                    if new_df is None or new_df.empty:
                        return load_gastos_fijos()

                    try:
                        # Convert new_df to dict rows
                        new_rows = new_df.to_dicts() if isinstance(new_df, pl.DataFrame) else new_df

                        old_ids = {r["id"] for r in gastos_fijos_state.value if "id" in r}
                        new_ids = {r.get("id") for r in new_rows if "id" in r}

                        # Deleted rows
                        for row_id in old_ids - new_ids:
                            gastos_fijos.delete(row_id)

                        # Updated or inserted rows
                        for row in new_rows:
                            if "id" in row and row["id"] in old_ids:
                                gastos_fijos.update(row["id"], row)
                            elif "id" not in row or not row["id"]:
                                gastos_fijos.insert(row)

                        gastos_fijos_state.value = new_rows
                        return load_gastos_fijos()
                    except Exception as e:
                        gr.Error(f"Error al guardar: {str(e)}")
                        return load_gastos_fijos()

                with gr.Row():
                    gr.Button("➕ Agregar fila", scale=1).click(
                        fn=lambda df: (df.vstack(pl.DataFrame({"id": [None], "gasto": [""], "total": [0]}))) if isinstance(df, pl.DataFrame) else df,
                        inputs=[gf_table],
                        outputs=[gf_table]
                    )
                    gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                        fn=save_gastos_fijos_changes,
                        inputs=[gf_table],
                        outputs=[gf_table]
                    )

            # Sub-tab 2: Ingresos
            with gr.Tab(label="Ingresos", id="ingresos_tab"):
                gr.Markdown("### Gestión de Ingresos")

                ingresos_state = gr.State(value=[])

                def load_ingresos():
                    rows = ingresos.get_all()
                    ingresos_state.value = rows
                    df = pl.DataFrame(rows) if rows else pl.DataFrame({"id": [], "tipo_ingreso": [], "total": [], "persona": []})
                    return df

                initial_ing = load_ingresos()
                ing_table = gr.Dataframe(
                    value=initial_ing,
                    interactive=True,
                    label="Ingresos"
                )

                def save_ingresos_changes(new_df):
                    """Diff and save changes to ingresos."""
                    if new_df is None or new_df.empty:
                        return load_ingresos()

                    try:
                        new_rows = new_df.to_dicts() if isinstance(new_df, pl.DataFrame) else new_df
                        old_ids = {r["id"] for r in ingresos_state.value if "id" in r}
                        new_ids = {r.get("id") for r in new_rows if "id" in r}

                        for row_id in old_ids - new_ids:
                            ingresos.delete(row_id)

                        for row in new_rows:
                            if "id" in row and row["id"] in old_ids:
                                ingresos.update(row["id"], row)
                            elif "id" not in row or not row["id"]:
                                ingresos.insert(row)

                        ingresos_state.value = new_rows
                        return load_ingresos()
                    except Exception as e:
                        gr.Error(f"Error al guardar: {str(e)}")
                        return load_ingresos()

                with gr.Row():
                    gr.Button("➕ Agregar fila", scale=1).click(
                        fn=lambda df: (df.vstack(pl.DataFrame({"id": [None], "tipo_ingreso": [""], "total": [0], "persona": [PERSONAS[0]]}))) if isinstance(df, pl.DataFrame) else df,
                        inputs=[ing_table],
                        outputs=[ing_table]
                    )
                    gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                        fn=save_ingresos_changes,
                        inputs=[ing_table],
                        outputs=[ing_table]
                    )

            # Sub-tab 3: Ahorros
            with gr.Tab(label="Ahorros", id="ahorros_tab"):
                gr.Markdown("### Gestión de Ahorros")

                ahorros_state = gr.State(value=[])

                def load_ahorros():
                    rows = ahorros.get_all()
                    ahorros_state.value = rows
                    df = pl.DataFrame(rows) if rows else pl.DataFrame({"id": [], "ahorro": [], "total": []})
                    return df

                initial_ah = load_ahorros()
                ah_table = gr.Dataframe(
                    value=initial_ah,
                    interactive=True,
                    label="Ahorros"
                )

                def save_ahorros_changes(new_df):
                    """Diff and save changes to ahorros."""
                    if new_df is None or new_df.empty:
                        return load_ahorros()

                    try:
                        new_rows = new_df.to_dicts() if isinstance(new_df, pl.DataFrame) else new_df
                        old_ids = {r["id"] for r in ahorros_state.value if "id" in r}
                        new_ids = {r.get("id") for r in new_rows if "id" in r}

                        for row_id in old_ids - new_ids:
                            ahorros.delete(row_id)

                        for row in new_rows:
                            if "id" in row and row["id"] in old_ids:
                                ahorros.update(row["id"], row)
                            elif "id" not in row or not row["id"]:
                                ahorros.insert(row)

                        ahorros_state.value = new_rows
                        return load_ahorros()
                    except Exception as e:
                        gr.Error(f"Error al guardar: {str(e)}")
                        return load_ahorros()

                with gr.Row():
                    gr.Button("➕ Agregar fila", scale=1).click(
                        fn=lambda df: (df.vstack(pl.DataFrame({"id": [None], "ahorro": [""], "total": [0]}))) if isinstance(df, pl.DataFrame) else df,
                        inputs=[ah_table],
                        outputs=[ah_table]
                    )
                    gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                        fn=save_ahorros_changes,
                        inputs=[ah_table],
                        outputs=[ah_table]
                    )

            # Sub-tab 4: Responsable de Gastos
            with gr.Tab(label="Responsable de Gastos", id="responsable_tab"):
                gr.Markdown("### Gestión de Responsables")

                resp_state = gr.State(value=[])

                def load_responsable():
                    rows = responsable_gastos.get_all()
                    resp_state.value = rows
                    df = pl.DataFrame(rows) if rows else pl.DataFrame({"id": [], "gasto": [], "responsable": [], "monto": []})
                    return df

                initial_resp = load_responsable()
                resp_table = gr.Dataframe(
                    value=initial_resp,
                    interactive=True,
                    label="Responsable de Gastos"
                )

                def save_responsable_changes(new_df):
                    """Diff and save changes to responsable_gastos."""
                    if new_df is None or new_df.empty:
                        return load_responsable()

                    try:
                        new_rows = new_df.to_dicts() if isinstance(new_df, pl.DataFrame) else new_df
                        old_ids = {r["id"] for r in resp_state.value if "id" in r}
                        new_ids = {r.get("id") for r in new_rows if "id" in r}

                        for row_id in old_ids - new_ids:
                            responsable_gastos.delete(row_id)

                        for row in new_rows:
                            if "id" in row and row["id"] in old_ids:
                                responsable_gastos.update(row["id"], row)
                            elif "id" not in row or not row["id"]:
                                responsable_gastos.insert(row)

                        resp_state.value = new_rows
                        return load_responsable()
                    except Exception as e:
                        gr.Error(f"Error al guardar: {str(e)}")
                        return load_responsable()

                with gr.Row():
                    gr.Button("➕ Agregar fila", scale=1).click(
                        fn=lambda df: (df.vstack(pl.DataFrame({"id": [None], "gasto": [""], "responsable": [RESPONSABLE_OPTIONS[0]], "monto": [0]}))) if isinstance(df, pl.DataFrame) else df,
                        inputs=[resp_table],
                        outputs=[resp_table]
                    )
                    gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                        fn=save_responsable_changes,
                        inputs=[resp_table],
                        outputs=[resp_table]
                    )

            # Sub-tab 5: Resumen (read-only, auto-calculated)
            with gr.Tab(label="Resumen", id="resumen_tab"):
                gr.Markdown("### Resumen de Ingresos y Gastos")

                def load_resumen():
                    ing_rows = ingresos.get_all()
                    gast_rows = gastos.get_all()
                    resp_rows = responsable_gastos.get_all()
                    df = resumen_transform.calc_resumen(ing_rows, gast_rows, resp_rows)
                    return df

                initial_resumen = load_resumen()
                resumen_table = gr.Dataframe(
                    value=initial_resumen,
                    interactive=False,
                    label="Resumen"
                )

                # Refresh resumen whenever any sub-tab saves
                # (In practice, we'd need to wire this in app.py or use a polling approach)
