import logging
from datetime import date

import gradio as gr

from models import fondos, presupuestos
from transforms import fondos as fondos_transform
from transforms import presupuestos as pres_transform
from ui.aviso_saldo import aviso_limites_saldo

logger = logging.getLogger(__name__)

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _choices_mes(hoy: date, n: int = 12) -> list[tuple[str, str]]:
    """Últimos n meses (el actual primero) como (etiqueta, 'AAAA-MM')."""
    opciones = []
    for i in range(n):
        m, a = hoy.month - i, hoy.year
        while m <= 0:
            m += 12
            a -= 1
        opciones.append((f"{MESES[m - 1].capitalize()} {a}", f"{a}-{m:02d}"))
    return opciones


def _render(valor_mes: str | None):
    """Lee el consumo del mes y devuelve (título, resumen HTML, tarjetas HTML, mensaje).

    Nunca lanza: si la lectura falla (p. ej. la tabla aún no existe) deja un mensaje
    visible en el panel y registra el error en el log.
    """
    hoy = date.today()
    try:
        anio, mes = (int(x) for x in (valor_mes or f"{hoy.year}-{hoy.month:02d}").split("-"))
    except ValueError:
        anio, mes = hoy.year, hoy.month
    nombre_mes = f"{MESES[mes - 1]} {anio}"
    titulo = f"### Presupuestos de {nombre_mes}"

    try:
        filas = presupuestos.get_consumo_mes(mes, anio)
    except Exception as e:
        if pres_transform.es_tabla_inexistente(e):
            logger.warning("Panel de Control: la tabla presupuestos no existe: %s", e)
            return titulo, "", "", f"⚠️ {pres_transform.MENSAJE_SIN_TABLA}"
        logger.exception("Panel de Control: no se pudo leer el consumo de presupuestos")
        return titulo, "", "", f"⚠️ No se pudieron leer los presupuestos: {e}"

    if not filas:
        return titulo, "", "", pres_transform.MENSAJE_SIN_PRESUPUESTOS

    tarjetas = pres_transform.armar_tarjetas(filas, mes, anio, hoy)
    res = pres_transform.resumen_panel(tarjetas)
    titulo = f"### {pres_transform.titulo_resumen(res, nombre_mes)}"
    return (
        titulo,
        pres_transform.html_resumen(res),
        pres_transform.html_tarjetas(tarjetas, mes, anio, hoy),
        "",
    )


def _msg_error(e: Exception) -> str:
    """Primera línea del error, para mostrarlo sin volcar SQL entero."""
    return (str(e).strip().splitlines() or [type(e).__name__])[0]


def _render_fondos():
    """Lee fondos y excesos y devuelve (título, aviso, tarjetas HTML, título del gráfico, figura).

    Cada bloque se lee una sola vez y falla por separado: si no se pueden leer los
    saldos, el aviso lo dice; si falla el gráfico de gasto con fondo, el mensaje va en su título. Nunca lanza.
    """
    titulo, aviso, html = "### Fondos de ahorro", "", ""
    try:
        saldos = fondos.get_saldos(date.today())
        try:
            retiros = fondos.get_retiros(limit=1000)
        except Exception as e:
            logger.exception("Panel de Control: no se pudieron leer los retiros de los fondos")
            retiros, aviso = [], f"⚠️ No se pudieron leer los últimos retiros: {_msg_error(e)}"
        if not saldos:
            aviso = fondos_transform.MENSAJE_SIN_FONDOS
        else:
            tarjetas = fondos_transform.armar_tarjetas(saldos, retiros)
            titulo = f"### {fondos_transform.titulo_fondos(tarjetas)}"
            html = fondos_transform.html_tarjetas(tarjetas)
            aviso = "\n\n".join(x for x in (fondos_transform.aviso_sin_saldo(tarjetas), aviso) if x)
    except Exception as e:
        logger.exception("Panel de Control: no se pudieron leer los fondos")
        aviso = f"⚠️ No se pudieron leer los fondos: {_msg_error(e)}"

    try:
        retiros_gasto = fondos.get_retiros(limit=1000)
        filas = fondos_transform.desglosar_retiros(retiros_gasto, fondos.get_excesos())
        exc_titulo = f"### {fondos_transform.titulo_gasto_fondo(filas)}"
        figura = fondos_transform.figura_gasto_fondo(filas)
    except Exception as e:
        logger.exception("Panel de Control: no se pudo armar el gasto pagado con fondo")
        exc_titulo = f"⚠️ No se pudo armar el gráfico de gasto con fondo: {_msg_error(e)}"
        figura = None
    return titulo, aviso, html, exc_titulo, figura


def _render_todo(valor_mes: str | None):
    """Refresco completo: presupuestos del mes elegido + fondos (siempre el mes en curso)."""
    return (*_render(valor_mes), *_render_fondos())


def build_tab():
    """Pestaña 'Panel de Control': presupuestos del mes y fondos de ahorro.

    Devuelve (fn_refresco, inputs, outputs) para conectarlo a `tab.select`.
    El selector de mes solo relee presupuestos; los fondos se leen al entrar a la pestaña.
    """
    hoy = date.today()
    choices = _choices_mes(hoy)

    gr.Markdown(
        "Compara lo gastado en cada categoría con su tope mensual. El gasto cuenta lo "
        "registrado por **cualquiera de los dos** (Marco y Chiara). La proyección a fin de "
        "mes sigue el ritmo actual (gastado ÷ días transcurridos × días del mes) y aparece "
        "desde el día 4. Estado: ✅ OK, ⚠️ a punto de excederse (≥ 80 % del tope o proyección "
        "por encima), 🔴 excedido (> 100 %)."
    )
    mes_dd = gr.Dropdown(choices=choices, value=choices[0][1], label="Mes", interactive=True)

    ini = _render(choices[0][1])
    titulo = gr.Markdown(ini[0])
    resumen = gr.HTML(ini[1])
    tarjetas = gr.HTML(ini[2])
    mensaje = gr.Markdown(ini[3])
    pres_outputs = [titulo, resumen, tarjetas, mensaje]
    mes_dd.change(fn=_render, inputs=[mes_dd], outputs=pres_outputs)

    gr.Markdown("---")
    gr.Markdown(
        "**Fondos de ahorro.** Saldo = saldo de partida + depósitos marcados − retiros "
        "(gastos «Pagado con fondo»), contando solo lo posterior al corte. Los retiros no "
        "consumen presupuestos ni son gasto de caja del mes, pero sí cuentan por categoría. "
        "Estado: ✅ saldo positivo, ⚠️ saldo bajo (menos de un aporte mensual), 🔴 saldo negativo."
    )
    aviso_limites_saldo(abierto=False)
    fi = _render_fondos()
    f_titulo = gr.Markdown(fi[0])
    f_aviso = gr.Markdown(fi[1])
    f_tarjetas = gr.HTML(fi[2])
    gr.Markdown("---")
    exc_titulo = gr.Markdown(fi[3])
    gr.Markdown(fondos_transform.NOTA_EXCESOS)
    exc_plot = gr.Plot(value=fi[4], label="Gasto pagado con fondo: cubierto y exceso por quién lo pagó")
    fondos_outputs = [f_titulo, f_aviso, f_tarjetas, exc_titulo, exc_plot]

    return _render_todo, [mes_dd], pres_outputs + fondos_outputs
