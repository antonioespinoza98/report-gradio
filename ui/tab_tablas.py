import gradio as gr
import polars as pl
from models import gastos_fijos, ingresos, ahorros, responsable_gastos, gastos
from transforms import resumen as resumen_transform
from utils.constants import PERSONAS, RESPONSABLE_OPTIONS

# ── helpers ────────────────────────────────────────────────────────────────────

def _safe_load(fn, empty_schema: dict):
    """Run fn(); return an empty DataFrame with given schema on any error."""
    try:
        return fn()
    except Exception:
        return pl.DataFrame(empty_schema)

def _to_polars(df) -> pl.DataFrame:
    """Ensure df is a Polars DataFrame (Gradio sometimes passes pandas)."""
    if isinstance(df, pl.DataFrame):
        return df
    return pl.from_pandas(df)

def _sync_table(display_df, state_rows: list[dict], model, display_cols: list[str]):
    """
    Diff display_df against state_rows and persist inserts/updates/deletes.

    Rules:
    - state_rows[i] matches display_df row i (same position = same record)
    - Rows beyond len(state_rows) in display_df are new inserts
    - Rows in state_rows beyond len(display_df) were deleted
    """
    if display_df is None:
        return state_rows

    new_rows = display_df.to_dicts() if isinstance(display_df, pl.DataFrame) else display_df
    n_old = len(state_rows)
    n_new = len(new_rows)

    # Deletes: old rows with no matching new row
    for i in range(n_new, n_old):
        row_id = state_rows[i].get("id")
        if row_id:
            model.delete(row_id)

    # Updates and inserts
    for i, row in enumerate(new_rows):
        data = {col: row.get(col) for col in display_cols}
        if i < n_old:
            row_id = state_rows[i].get("id")
            if row_id:
                model.update(row_id, data)
        else:
            model.insert(data)

# ── Tab builder ────────────────────────────────────────────────────────────────

def build_tab():
    """Build the 'Tablas Predeterminadas' tab with 5 sub-tabs."""

    with gr.Tabs():

        # ── Sub-tab 1: Gastos Fijos ────────────────────────────────────────────
        with gr.Tab(label="Gastos Fijos"):
            gr.Markdown("### Gestión de Gastos Fijos")

            gf_state = gr.State(value=[])

            def load_gf():
                rows = gastos_fijos.get_all()
                gf_state.value = rows
                data = {"Gasto": [r["gasto"] for r in rows], "Total": [r["total"] for r in rows]}
                return pl.DataFrame(data) if rows else pl.DataFrame({"Gasto": [], "Total": []})

            gf_table = gr.Dataframe(
                value=_safe_load(load_gf, {"Gasto": [], "Total": []}),
                interactive=True,
                label="Gastos Fijos"
            )

            def save_gf(df, state):
                df = _to_polars(df)
                try:
                    _sync_table(df, state, gastos_fijos, ["gasto", "total"])
                    new_rows = gastos_fijos.get_all()
                    gf_state.value = new_rows
                    return pl.DataFrame({"Gasto": [r["gasto"] for r in new_rows], "Total": [r["total"] for r in new_rows]}), new_rows
                except Exception as e:
                    gr.Error(f"Error al guardar: {e}")
                    return df, state

            with gr.Row():
                gr.Button("➕ Agregar fila", scale=1).click(
                    fn=lambda df: df.vstack(pl.DataFrame({"Gasto": [""], "Total": [0.0]})) if isinstance(df, pl.DataFrame) else df,
                    inputs=[gf_table], outputs=[gf_table]
                )
                gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                    fn=save_gf, inputs=[gf_table, gf_state], outputs=[gf_table, gf_state]
                )

        # ── Sub-tab 2: Ingresos ────────────────────────────────────────────────
        with gr.Tab(label="Ingresos"):
            gr.Markdown("### Gestión de Ingresos")

            ing_state = gr.State(value=[])

            def load_ing():
                rows = ingresos.get_all()
                ing_state.value = rows
                data = {
                    "Tipo de ingreso": [r["tipo_ingreso"] for r in rows],
                    "Total": [r["total"] for r in rows],
                    "Persona": [r["persona"] for r in rows],
                }
                return pl.DataFrame(data) if rows else pl.DataFrame({"Tipo de ingreso": [], "Total": [], "Persona": []})

            ing_table = gr.Dataframe(
                value=_safe_load(load_ing, {"Tipo de ingreso": [], "Total": [], "Persona": []}),
                interactive=True,
                label="Ingresos"
            )

            def save_ing(df, state):
                df = _to_polars(df)
                try:
                    new_rows_raw = df.to_dicts() if isinstance(df, pl.DataFrame) else df
                    # Remap display col names → DB col names
                    mapped = [{"tipo_ingreso": r.get("Tipo de ingreso", ""), "total": r.get("Total", 0), "persona": r.get("Persona", PERSONAS[0])} for r in new_rows_raw]
                    mapped_df = pl.DataFrame(mapped)
                    _sync_table(mapped_df, state, ingresos, ["tipo_ingreso", "total", "persona"])
                    new_rows = ingresos.get_all()
                    ing_state.value = new_rows
                    data = {"Tipo de ingreso": [r["tipo_ingreso"] for r in new_rows], "Total": [r["total"] for r in new_rows], "Persona": [r["persona"] for r in new_rows]}
                    return pl.DataFrame(data) if new_rows else pl.DataFrame({"Tipo de ingreso": [], "Total": [], "Persona": []}), new_rows
                except Exception as e:
                    gr.Error(f"Error al guardar: {e}")
                    return df, state

            with gr.Row():
                gr.Button("➕ Agregar fila", scale=1).click(
                    fn=lambda df: df.vstack(pl.DataFrame({"Tipo de ingreso": [""], "Total": [0.0], "Persona": [PERSONAS[0]]})) if isinstance(df, pl.DataFrame) else df,
                    inputs=[ing_table], outputs=[ing_table]
                )
                gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                    fn=save_ing, inputs=[ing_table, ing_state], outputs=[ing_table, ing_state]
                )

        # ── Sub-tab 3: Ahorros ─────────────────────────────────────────────────
        with gr.Tab(label="Ahorros"):
            gr.Markdown("### Gestión de Ahorros")

            ah_state = gr.State(value=[])

            def load_ah():
                rows = ahorros.get_all()
                ah_state.value = rows
                data = {"Ahorro": [r["ahorro"] for r in rows], "Total": [r["total"] for r in rows]}
                return pl.DataFrame(data) if rows else pl.DataFrame({"Ahorro": [], "Total": []})

            ah_table = gr.Dataframe(
                value=_safe_load(load_ah, {"Ahorro": [], "Total": []}),
                interactive=True,
                label="Ahorros"
            )

            def save_ah(df, state):
                df = _to_polars(df)
                try:
                    new_rows_raw = df.to_dicts() if isinstance(df, pl.DataFrame) else df
                    mapped = [{"ahorro": r.get("Ahorro", ""), "total": r.get("Total", 0)} for r in new_rows_raw]
                    mapped_df = pl.DataFrame(mapped)
                    _sync_table(mapped_df, state, ahorros, ["ahorro", "total"])
                    new_rows = ahorros.get_all()
                    ah_state.value = new_rows
                    data = {"Ahorro": [r["ahorro"] for r in new_rows], "Total": [r["total"] for r in new_rows]}
                    return pl.DataFrame(data) if new_rows else pl.DataFrame({"Ahorro": [], "Total": []}), new_rows
                except Exception as e:
                    gr.Error(f"Error al guardar: {e}")
                    return df, state

            with gr.Row():
                gr.Button("➕ Agregar fila", scale=1).click(
                    fn=lambda df: df.vstack(pl.DataFrame({"Ahorro": [""], "Total": [0.0]})) if isinstance(df, pl.DataFrame) else df,
                    inputs=[ah_table], outputs=[ah_table]
                )
                gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                    fn=save_ah, inputs=[ah_table, ah_state], outputs=[ah_table, ah_state]
                )

        # ── Sub-tab 4: Responsable de Gastos ──────────────────────────────────
        with gr.Tab(label="Responsable de Gastos"):
            gr.Markdown("### Gestión de Responsables")

            resp_state = gr.State(value=[])

            def load_resp():
                rows = responsable_gastos.get_all()
                resp_state.value = rows
                data = {
                    "Gasto": [r["gasto"] for r in rows],
                    "Responsable": [r["responsable"] for r in rows],
                    "Monto": [r["monto"] for r in rows],
                }
                return pl.DataFrame(data) if rows else pl.DataFrame({"Gasto": [], "Responsable": [], "Monto": []})

            resp_table = gr.Dataframe(
                value=_safe_load(load_resp, {"Gasto": [], "Responsable": [], "Monto": []}),
                interactive=True,
                label="Responsable de Gastos"
            )

            def save_resp(df, state):
                df = _to_polars(df)
                try:
                    new_rows_raw = df.to_dicts() if isinstance(df, pl.DataFrame) else df
                    mapped = [{"gasto": r.get("Gasto", ""), "responsable": r.get("Responsable", RESPONSABLE_OPTIONS[0]), "monto": r.get("Monto", 0)} for r in new_rows_raw]
                    mapped_df = pl.DataFrame(mapped)
                    _sync_table(mapped_df, state, responsable_gastos, ["gasto", "responsable", "monto"])
                    new_rows = responsable_gastos.get_all()
                    resp_state.value = new_rows
                    data = {"Gasto": [r["gasto"] for r in new_rows], "Responsable": [r["responsable"] for r in new_rows], "Monto": [r["monto"] for r in new_rows]}
                    return pl.DataFrame(data) if new_rows else pl.DataFrame({"Gasto": [], "Responsable": [], "Monto": []}), new_rows
                except Exception as e:
                    gr.Error(f"Error al guardar: {e}")
                    return df, state

            with gr.Row():
                gr.Button("➕ Agregar fila", scale=1).click(
                    fn=lambda df: df.vstack(pl.DataFrame({"Gasto": [""], "Responsable": [RESPONSABLE_OPTIONS[0]], "Monto": [0.0]})) if isinstance(df, pl.DataFrame) else df,
                    inputs=[resp_table], outputs=[resp_table]
                )
                gr.Button("💾 Guardar cambios", variant="primary", scale=1).click(
                    fn=save_resp, inputs=[resp_table, resp_state], outputs=[resp_table, resp_state]
                )

        # ── Sub-tab 5: Resumen ─────────────────────────────────────────────────
        with gr.Tab(label="Resumen"):
            gr.Markdown("### Resumen de Ingresos y Gastos")

            def load_resumen():
                ing_rows = ingresos.get_all()
                gast_rows = gastos.get_all()
                resp_rows = responsable_gastos.get_all()
                return resumen_transform.calc_resumen(ing_rows, gast_rows, resp_rows)

            resumen_table = gr.Dataframe(
                value=_safe_load(load_resumen, {"Persona": [], "Ingreso": [], "Total Gasto": [], "Sobrante": []}),
                interactive=False,
                label="Resumen"
            )
