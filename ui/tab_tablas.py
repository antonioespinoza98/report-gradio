import logging
import gradio as gr
import polars as pl
from datetime import date
from ui import tab_resumen_mes
from models import gastos_fijos, ingresos, ahorros, responsable_gastos, gastos, presupuestos, fondos
from transforms import fondos as fondos_transform
from ui.aviso_saldo import aviso_limites_saldo
from transforms import resumen as resumen_transform
from transforms import presupuestos as presupuestos_transform
from utils.constants import PERSONAS, CATEGORIAS, RESPONSABLE_OPTIONS
from utils.money import eur

logger = logging.getLogger(__name__)

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

# ── Presupuestos ───────────────────────────────────────────────────────────────

_PR_COLS = ["Nombre", "Categoría", "Tope mensual (€)", "Responsable"]
_PR_SCHEMA = {"Nombre": pl.Utf8, "Categoría": pl.Utf8, "Tope mensual (€)": pl.Float64, "Responsable": pl.Utf8}
_PR_NUEVO = 0  # valor del selector para «crear uno nuevo»


def _pr_df(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "Nombre": [r["nombre"] for r in rows],
            "Categoría": [r["categoria"] for r in rows],
            "Tope mensual (€)": [float(r["monto_mensual"]) for r in rows],
            "Responsable": [r["responsable"] for r in rows],
        },
        schema=_PR_SCHEMA,
    )


def _pr_choices(rows: list[dict]):
    return [("➕ Nuevo presupuesto", _PR_NUEVO)] + [(r["nombre"], r["id"]) for r in rows]


def _pr_aviso(rows: list[dict], error: str | None = None) -> str:
    """Texto bajo la tabla: error de lectura o categorías con más de un presupuesto."""
    if error:
        return error
    repetidas = presupuestos_transform.avisos_categoria_repetida(rows)
    if not repetidas:
        return ""
    cats = ", ".join(f"«{c}»" for c in repetidas)
    return (f"⚠️ Hay más de un presupuesto en la categoría {cats}: el consumo de esa "
            "categoría se cuenta completo en cada uno (no se reparte).")


def _build_presupuestos():
    """Sub-tab 'Presupuestos': tope mensual por categoría, editable desde la interfaz.

    A diferencia de los otros sub-tabs, no usa un gr.Dataframe editable: una celda de
    Dataframe admite texto libre y la categoría/responsable deben ser listas cerradas.
    Se usa una tabla de solo lectura más un formulario con desplegables; la
    validación final vive en models.presupuestos.validar_presupuesto.
    """
    gr.Markdown(
        "### Presupuestos mensuales\n"
        "Tope mensual por categoría. Lo gastado se toma de los **gastos variables** de esa "
        "categoría (de Marco y de Chiara) y se compara en la pestaña *Panel de Control*."
    )

    try:
        filas0, error0 = presupuestos.get_all(), None
    except Exception as e:
        logger.exception("Presupuestos: no se pudo leer la tabla")
        filas0 = []
        if presupuestos_transform.es_tabla_inexistente(e):
            error0 = f"⚠️ {presupuestos_transform.MENSAJE_SIN_TABLA}"
        else:
            error0 = f"⚠️ No se pudieron leer los presupuestos: {e}"

    pr_state = gr.State(value=filas0)
    pr_table = gr.Dataframe(value=_pr_df(filas0), interactive=False, label="Presupuestos")
    pr_aviso = gr.Markdown(_pr_aviso(filas0, error0))

    with gr.Group():
        pr_sel = gr.Dropdown(
            choices=_pr_choices(filas0), value=_PR_NUEVO, label="Presupuesto a editar",
            info="Elegí uno existente para modificarlo o eliminarlo, o «Nuevo presupuesto».",
        )
        with gr.Row():
            pr_nombre = gr.Textbox(label="Nombre", placeholder="Ej: Supermercado")
            pr_cat = gr.Dropdown(choices=CATEGORIAS, value=CATEGORIAS[0], label="Categoría")
            pr_monto = gr.Number(label="Tope mensual (€)", value=0, precision=2, minimum=0)
            pr_resp = gr.Dropdown(choices=RESPONSABLE_OPTIONS, value=RESPONSABLE_OPTIONS[0],
                                  label="Responsable")

    form = [pr_nombre, pr_cat, pr_monto, pr_resp]

    def _form_vacio():
        return "", CATEGORIAS[0], 0, RESPONSABLE_OPTIONS[0]

    def _recargar(sel_value=_PR_NUEVO):
        """Relee la tabla y devuelve (tabla, estado, selector, aviso) coherentes."""
        rows = presupuestos.get_all()
        ids = {r["id"] for r in rows}
        sel = sel_value if sel_value in ids else _PR_NUEVO
        return (_pr_df(rows), rows, gr.update(choices=_pr_choices(rows), value=sel),
                _pr_aviso(rows))

    def on_select(sel, state):
        fila = next((r for r in state if r["id"] == sel), None)
        if fila is None:
            return _form_vacio()
        return fila["nombre"], fila["categoria"], float(fila["monto_mensual"]), fila["responsable"]

    def on_guardar(sel, nombre, categoria, monto, responsable):
        data = {"nombre": nombre, "categoria": categoria,
                "monto_mensual": monto, "responsable": responsable}
        try:
            if sel and sel != _PR_NUEVO:
                if presupuestos.update(sel, data) is None:
                    raise ValueError("Ese presupuesto ya no existe. Recargá la lista.")
            else:
                presupuestos.insert(data)
            salida = _recargar(_PR_NUEVO)
        except ValueError as e:
            raise gr.Error(str(e))
        except Exception as e:
            logger.exception("Presupuestos: error al guardar")
            if presupuestos_transform.es_tabla_inexistente(e):
                raise gr.Error(presupuestos_transform.MENSAJE_SIN_TABLA)
            raise gr.Error(f"Error al guardar el presupuesto: {e}")
        gr.Info("Presupuesto guardado.")
        return (*salida, *_form_vacio())

    def on_eliminar(sel):
        if not sel or sel == _PR_NUEVO:
            raise gr.Error("Elegí primero el presupuesto que querés eliminar.")
        try:
            presupuestos.delete(sel)
            salida = _recargar(_PR_NUEVO)
        except Exception as e:
            logger.exception("Presupuestos: error al eliminar")
            if presupuestos_transform.es_tabla_inexistente(e):
                raise gr.Error(presupuestos_transform.MENSAJE_SIN_TABLA)
            raise gr.Error(f"Error al eliminar el presupuesto: {e}")
        gr.Info("Presupuesto eliminado.")
        return (*salida, *_form_vacio())

    salidas = [pr_table, pr_state, pr_sel, pr_aviso, *form]
    pr_sel.change(fn=on_select, inputs=[pr_sel, pr_state], outputs=form)
    with gr.Row():
        gr.Button("💾 Guardar presupuesto", variant="primary", scale=1).click(
            fn=on_guardar, inputs=[pr_sel, *form], outputs=salidas
        )
        gr.Button("🗑️ Eliminar", variant="stop", scale=1).click(
            fn=on_eliminar, inputs=[pr_sel], outputs=salidas
        )


# ── Ahorros (fondos) ───────────────────────────────────────────────────────────

_AH_NUEVO = 0  # valor del selector para «crear uno nuevo»


def _msg_error(e: Exception) -> str:
    return (str(e).strip().splitlines() or [type(e).__name__])[0]


def _ah_leer():
    """Devuelve (filas combinadas con saldo, error de lectura de saldos o None).

    Si falla la lectura de ahorros se propaga; si solo fallan los saldos, la lista y el
    formulario siguen funcionando y el error se muestra bajo la tabla.
    """
    rows = ahorros.get_all()
    try:
        return fondos_transform.combinar_ahorros(rows, fondos.get_saldos()), None
    except Exception as e:
        logger.exception("Ahorros: no se pudieron leer los saldos")
        return (fondos_transform.combinar_ahorros(rows, None),
                f"⚠️ No se pudieron leer los saldos de los fondos: {_msg_error(e)}")


def _ah_choices(filas: list[dict]):
    return [("➕ Nuevo ahorro", _AH_NUEVO)] + [(f["ahorro"], f["id"]) for f in filas]


def _build_ahorros():
    """Sub-tab 'Ahorros': cada ahorro es un fondo con saldo, editado POR ID.

    Antes era una tabla editable sincronizada por posición; con fondos eso es peligroso
    (borrar una fila del medio desplaza ids y, por cascada, se perderían saldo y
    retiros). Ahora hay una tabla de solo lectura y un formulario con selector.
    """
    gr.Markdown(
        "### Ahorros (fondos)\n"
        "Cada ahorro es un **fondo**: saldo = saldo de partida + depósitos marcados en *Resumen del "
        "Mes* − retiros (gastos *Pagado con fondo*), contando solo lo posterior a la fecha de corte. "
        "El nombre debe coincidir con el de *Responsable de Gastos*: de ahí sale el monto de cada "
        "depósito, así que si lo cambiás, actualizá también esa tabla."
    )
    aviso_limites_saldo(abierto=True)

    try:
        filas0, error0 = _ah_leer()
    except Exception as e:
        logger.exception("Ahorros: no se pudo leer la tabla")
        filas0, error0 = [], f"⚠️ No se pudieron leer los ahorros: {_msg_error(e)}"

    ah_state = gr.State(value=filas0)
    ah_table = gr.Dataframe(value=fondos_transform.tabla_ahorros(filas0), interactive=False,
                            label="Ahorros y saldos")
    ah_aviso = gr.Markdown(fondos_transform.aviso_ahorros(filas0, error0))

    with gr.Group():
        ah_sel = gr.Dropdown(
            choices=_ah_choices(filas0), value=_AH_NUEVO, label="Ahorro a editar",
            info="Elegí uno existente para modificarlo, eliminarlo o cargar su saldo, o «Nuevo ahorro».",
        )
        with gr.Row():
            ah_nombre = gr.Textbox(label="Ahorro", placeholder="Ej: Viajes")
            ah_aporte = gr.Number(label="Aporte mensual total (€)", value=0, precision=2, minimum=0)
        ah_detalle = gr.Markdown(fondos_transform.detalle_fondo(None))

    form = [ah_nombre, ah_aporte]

    def _form_vacio():
        return "", 0

    def _recargar(sel_value=_AH_NUEVO):
        """Relee y devuelve (tabla, estado, selector, aviso, detalle) coherentes."""
        filas, error = _ah_leer()
        por_id = {f["id"]: f for f in filas}
        sel = sel_value if sel_value in por_id else _AH_NUEVO
        return (fondos_transform.tabla_ahorros(filas), filas,
                gr.update(choices=_ah_choices(filas), value=sel),
                fondos_transform.aviso_ahorros(filas, error),
                fondos_transform.detalle_fondo(por_id.get(sel)))

    def on_select(sel, state):
        fila = next((f for f in state if f["id"] == sel), None)
        if fila is None:
            return (*_form_vacio(), fondos_transform.detalle_fondo(None))
        return fila["ahorro"], float(fila["total"]), fondos_transform.detalle_fondo(fila)

    def on_guardar(sel, nombre, aporte):
        nombre = (nombre or "").strip()
        try:
            if not nombre:
                raise ValueError("El nombre del ahorro no puede estar vacío.")
            if aporte is None or float(aporte) < 0:
                raise ValueError("El aporte mensual debe ser un número mayor o igual a 0.")
            data = {"ahorro": nombre, "total": aporte}
            if sel and sel != _AH_NUEVO:
                if ahorros.update(sel, data) is None:
                    raise ValueError("Ese ahorro ya no existe. Recargá la lista.")
            else:
                ahorros.insert(data)
            salida = _recargar(_AH_NUEVO)
        except ValueError as e:
            raise gr.Error(str(e))
        except Exception as e:
            logger.exception("Ahorros: error al guardar")
            if getattr(e, "pgcode", None) == "23505":
                raise gr.Error("Ya existe un ahorro con ese nombre.")
            raise gr.Error(f"Error al guardar el ahorro: {_msg_error(e)}")
        gr.Info("Ahorro guardado.")
        return (*salida, *_form_vacio())

    def on_eliminar(sel, confirmar):
        if not sel or sel == _AH_NUEVO:
            raise gr.Error("Elegí primero el ahorro que querés eliminar.")
        if not confirmar:
            raise gr.Error("Marcá la casilla de confirmación para eliminar el fondo.")
        try:
            ahorros.delete(sel)
            salida = _recargar(_AH_NUEVO)
        except Exception as e:
            logger.exception("Ahorros: error al eliminar")
            raise gr.Error(f"Error al eliminar el ahorro: {_msg_error(e)}")
        gr.Info("Fondo eliminado. Sus retiros pasaron a ser gastos normales y se perdió su tracker de depósitos.")
        return (*salida, *_form_vacio(), False)

    salidas = [ah_table, ah_state, ah_sel, ah_aviso, ah_detalle, *form]
    ah_sel.change(fn=on_select, inputs=[ah_sel, ah_state], outputs=[*form, ah_detalle])
    with gr.Row():
        gr.Button("💾 Guardar ahorro", variant="primary", scale=1).click(
            fn=on_guardar, inputs=[ah_sel, *form], outputs=salidas
        )
    with gr.Group():
        gr.Markdown(
            "**Eliminar un fondo** hace que sus retiros pasen a ser gastos normales (cuentan como "
            "gasto de caja) y se pierde el tracker de depósitos del fondo. No se puede deshacer."
        )
        ah_confirmar = gr.Checkbox(label="Confirmo que quiero eliminar el ahorro elegido", value=False)
        gr.Button("🗑️ Eliminar", variant="stop").click(
            fn=on_eliminar, inputs=[ah_sel, ah_confirmar], outputs=[*salidas, ah_confirmar]
        )

    gr.Markdown(
        "#### Saldo actual del fondo\n"
        "Cargá lo que tiene el fondo **HOY**, según tu cuenta; los depósitos y retiros nuevos se "
        "suman o restan desde este momento. Volver a cargarlo mueve el corte: lo anterior queda "
        "absorbido en el nuevo saldo."
    )
    with gr.Row():
        ah_saldo = gr.Number(label="Saldo actual según tu cuenta (€)", value=None, precision=2, minimum=0)
        ah_fijar = gr.Button("📌 Fijar saldo actual", variant="secondary")
    ah_confirm = gr.Markdown("")

    def on_fijar(sel, saldo):
        if not sel or sel == _AH_NUEVO:
            raise gr.Error("Elegí primero el ahorro cuyo saldo querés cargar.")
        try:
            res = ahorros.fijar_saldo_inicial(sel, saldo)
        except ValueError as e:
            raise gr.Error(str(e))
        except Exception as e:
            logger.exception("Ahorros: error al fijar el saldo")
            raise gr.Error(f"Error al fijar el saldo: {_msg_error(e)}")
        if res is None:
            raise gr.Error("Ese ahorro ya no existe. Recargá la lista.")
        try:
            salida = _recargar(sel)
        except Exception as e:
            # El saldo ya quedó guardado: solo falló releer la lista.
            logger.exception("Ahorros: saldo fijado pero no se pudo releer")
            salida = tuple(gr.update() for _ in range(5))
        texto = (f"✅ Saldo de «{res['ahorro']}» fijado en {eur(res['saldo_inicial'])} el "
                 f"{fondos_transform.fmt_fecha(res['fecha_corte'])}. Los depósitos y retiros nuevos "
                 "se suman o restan desde ahora.")
        gr.Info(texto.removeprefix("✅ "))
        return (*salida, None, texto)

    ah_fijar.click(fn=on_fijar, inputs=[ah_sel, ah_saldo], outputs=[*salidas[:5], ah_saldo, ah_confirm])


# ── Tab builder ────────────────────────────────────────────────────────────────

def build_tab():
    """Pestaña 'Gastos Fijos' con 7 sub-tabs (la última es 'Resumen del Mes').

    Devuelve (fn_refresco, inputs, outputs, subtab) del tracker mensual para que
    app.py lo conecte a `subtab.select`.
    """

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
                    mapped = [{"gasto": r.get("Gasto", ""), "total": r.get("Total", 0)} for r in df.to_dicts()]
                    _sync_table(pl.DataFrame(mapped), state, gastos_fijos, ["gasto", "total"])
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

        # ── Sub-tab 3: Ahorros (fondos con saldo) ──────────────────────────────
        with gr.Tab(label="Ahorros"):
            _build_ahorros()

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

        # ── Sub-tab 5: Presupuestos ────────────────────────────────────────────
        with gr.Tab(label="Presupuestos"):
            _build_presupuestos()

        # ── Sub-tab 6: Resumen ─────────────────────────────────────────────────
        with gr.Tab(label="Resumen"):
            gr.Markdown("### Resumen de Ingresos y Gastos")
            gr.Markdown("*El gasto variable no incluye los gastos pagados con un fondo de ahorro: "
                        "no son gasto de caja del mes.*")

            def _month_choices():
                today = date.today()
                choices = []
                for i in range(12):
                    month = today.month - i
                    year = today.year
                    while month <= 0:
                        month += 12
                        year -= 1
                    choices.append(f"{year}-{month:02d}")
                return choices

            resumen_mes = gr.Dropdown(
                choices=_month_choices(),
                value=_month_choices()[0],
                label="Mes",
                interactive=True,
            )

            def load_resumen(mes: str):
                year, month = int(mes.split("-")[0]), int(mes.split("-")[1])
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                date_from = date(year, month, 1)
                date_to = date(year, month, last_day)

                ing_rows = ingresos.get_all()
                # Los retiros de fondos no son gasto de caja del mes
                gast_rows = gastos.get_filtered(date_from=date_from, date_to=date_to, excluir_retiros=True)
                resp_rows = responsable_gastos.get_all()
                fijos_rows = gastos_fijos.get_all()
                return resumen_transform.calc_resumen(ing_rows, gast_rows, resp_rows, fijos_rows)

            empty_schema = {"Persona": [], "Ingreso": [], "Gasto Variable": [], "Gasto Fijo": [], "Sobrante": []}

            resumen_table = gr.Dataframe(
                value=_safe_load(lambda: load_resumen(_month_choices()[0]), empty_schema),
                interactive=False,
                label="Resumen"
            )

            resumen_mes.change(fn=load_resumen, inputs=[resumen_mes], outputs=[resumen_table])

        # ── Sub-tab 7: Resumen del Mes (tracker de pagos y ahorros) ───────────
        with gr.Tab(label="Resumen del Mes", id="subtab_resumen_mes") as subtab_resumen_mes:
            resumen_fn, resumen_inputs, resumen_outputs = tab_resumen_mes.build_tab()

    return resumen_fn, resumen_inputs, resumen_outputs, subtab_resumen_mes
