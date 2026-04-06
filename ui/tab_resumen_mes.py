import gradio as gr
import polars as pl
from datetime import datetime
from models import pagos_fijos, gastos_fijos, pagos_ahorros, ahorros
from utils.constants import PERSONAS


def build_tab():
    """Build the 'Resumen del Mes' tab with payment and savings deposit trackers."""

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

    # ── helpers ────────────────────────────────────────────────────────────────

    def _parse_mes_anio(mes, anio):
        return (int(mes) if isinstance(mes, float) else mes,
                int(anio) if isinstance(anio, float) else anio)

    def to_bool(val):
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    def _pivot(rows_df: pl.DataFrame, name_col: str) -> pl.DataFrame:
        """Pivot (name, persona, pagado) → (Name, Marco, Chiara)."""
        if rows_df.is_empty():
            return pl.DataFrame(schema={name_col: pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})
        pivot_data = []
        for name in rows_df[name_col].unique():
            name_rows = rows_df.filter(pl.col(name_col) == name)
            row_data = {name_col: name}
            for persona in PERSONAS:
                p_row = name_rows.filter(pl.col("persona") == persona)
                row_data[persona] = bool(p_row["pagado"][0]) if not p_row.is_empty() else False
            pivot_data.append(row_data)
        return pl.DataFrame(pivot_data)

    # ── Gastos Fijos ────────────────────────────────────────────────────────────

    def load_pagos_fijos(mes, anio):
        mes, anio = _parse_mes_anio(mes, anio)
        pagos_fijos.get_or_create_for_month(mes, anio)

        pf_rows = pagos_fijos.get_all()
        pf_df = pl.DataFrame(pf_rows) if pf_rows else pl.DataFrame()
        if not pf_df.is_empty():
            pf_df = pf_df.filter((pl.col("mes") == mes) & (pl.col("anio") == anio))

        gf_rows = gastos_fijos.get_all()
        gf_df = pl.DataFrame(gf_rows) if gf_rows else pl.DataFrame()

        if not pf_df.is_empty() and not gf_df.is_empty():
            pf_df = pf_df.join(gf_df, left_on="gasto_fijo_id", right_on="id")
            pf_df = pf_df.select(["gasto", "persona", "pagado"])

        return _pivot(pf_df, "Gasto") if not pf_df.is_empty() else \
            pl.DataFrame(schema={"Gasto": pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})

    # ── Ahorros ─────────────────────────────────────────────────────────────────

    def load_pagos_ahorros(mes, anio):
        mes, anio = _parse_mes_anio(mes, anio)
        pagos_ahorros.get_or_create_for_month(mes, anio)

        pa_rows = pagos_ahorros.get_all()
        pa_df = pl.DataFrame(pa_rows) if pa_rows else pl.DataFrame()
        if not pa_df.is_empty():
            pa_df = pa_df.filter((pl.col("mes") == mes) & (pl.col("anio") == anio))

        ah_rows = ahorros.get_all()
        ah_df = pl.DataFrame(ah_rows) if ah_rows else pl.DataFrame()

        if not pa_df.is_empty() and not ah_df.is_empty():
            pa_df = pa_df.join(ah_df, left_on="ahorro_id", right_on="id")
            pa_df = pa_df.select(["ahorro", "persona", "pagado"])

        return _pivot(pa_df, "Ahorro") if not pa_df.is_empty() else \
            pl.DataFrame(schema={"Ahorro": pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})

    def load_both(mes, anio):
        return load_pagos_fijos(mes, anio), load_pagos_ahorros(mes, anio)

    # ── UI — Gastos Fijos ───────────────────────────────────────────────────────

    gr.Markdown("### Tracking de Pagos de Gastos Fijos")
    try:
        initial_fijos = load_pagos_fijos(current_month, current_year)
    except Exception:
        initial_fijos = pl.DataFrame(schema={"Gasto": pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})

    payment_table = gr.Dataframe(
        value=initial_fijos,
        interactive=True,
        label="Estado de pagos — marca los checkboxes y presiona Guardar"
    )
    save_fijos_btn = gr.Button("💾 Guardar pagos", variant="primary")

    def on_save_fijos(updated_df, mes, anio):
        if updated_df is None:
            return load_pagos_fijos(mes, anio)
        rows_data = updated_df.to_dicts() if isinstance(updated_df, pl.DataFrame) \
            else updated_df.to_dict(orient="records")
        if not rows_data:
            return load_pagos_fijos(mes, anio)
        try:
            mes, anio = _parse_mes_anio(mes, anio)
            gf_map = {r["gasto"]: r["id"] for r in gastos_fijos.get_all()}
            for row in rows_data:
                gid = gf_map.get(row["Gasto"])
                if gid:
                    for persona in PERSONAS:
                        pagos_fijos.toggle_pago(gid, persona, mes, anio, to_bool(row.get(persona, False)))
            return load_pagos_fijos(mes, anio)
        except Exception as e:
            gr.Error(f"Error al guardar: {str(e)}")
            return load_pagos_fijos(mes, anio)

    # ── UI — Ahorros ────────────────────────────────────────────────────────────

    gr.Markdown("### Tracking de Depósitos de Ahorro")
    try:
        initial_ahorros = load_pagos_ahorros(current_month, current_year)
    except Exception:
        initial_ahorros = pl.DataFrame(schema={"Ahorro": pl.Utf8, "Marco": pl.Boolean, "Chiara": pl.Boolean})

    ahorros_table = gr.Dataframe(
        value=initial_ahorros,
        interactive=True,
        label="Estado de depósitos — marca los checkboxes y presiona Guardar"
    )
    save_ahorros_btn = gr.Button("💾 Guardar depósitos", variant="primary")

    def on_save_ahorros(updated_df, mes, anio):
        if updated_df is None:
            return load_pagos_ahorros(mes, anio)
        rows_data = updated_df.to_dicts() if isinstance(updated_df, pl.DataFrame) \
            else updated_df.to_dict(orient="records")
        if not rows_data:
            return load_pagos_ahorros(mes, anio)
        try:
            mes, anio = _parse_mes_anio(mes, anio)
            ah_map = {r["ahorro"]: r["id"] for r in ahorros.get_all()}
            for row in rows_data:
                aid = ah_map.get(row["Ahorro"])
                if aid:
                    for persona in PERSONAS:
                        pagos_ahorros.toggle_pago(aid, persona, mes, anio, to_bool(row.get(persona, False)))
            return load_pagos_ahorros(mes, anio)
        except Exception as e:
            gr.Error(f"Error al guardar: {str(e)}")
            return load_pagos_ahorros(mes, anio)

    # ── Events ──────────────────────────────────────────────────────────────────

    mes_input.change(fn=load_both, inputs=[mes_input, anio_input], outputs=[payment_table, ahorros_table])
    anio_input.change(fn=load_both, inputs=[mes_input, anio_input], outputs=[payment_table, ahorros_table])
    save_fijos_btn.click(fn=on_save_fijos, inputs=[payment_table, mes_input, anio_input], outputs=[payment_table])
    save_ahorros_btn.click(fn=on_save_ahorros, inputs=[ahorros_table, mes_input, anio_input], outputs=[ahorros_table])

    return load_both, mes_input, anio_input, payment_table, ahorros_table
