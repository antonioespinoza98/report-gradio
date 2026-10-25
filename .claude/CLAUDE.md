# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Gradio app (Spanish UI) for tracking shared expenses between Marco and Chiara. Postgres (Supabase) for storage, Polars for transforms, Plotly for charts. Deployed as a Hugging Face Space: pushing to `main` triggers `.github/workflows/main.yml`, which force-syncs the repo to the HF Space (the README front-matter configures the Space).

## Commands

- Install: `pip install -r requirements.txt` (a `.venv` exists in the repo)
- Run: `python app.py` (serves on `0.0.0.0:7860`)
- No test suite or linter is configured.

## Configuration

`.env` (see `.env.example`): `DATABASE_URL`, `DB_SCHEMA`, `RUN_MIGRATIONS`.
- `DB_SCHEMA` sets the connection `search_path`; the tables live in the **`public`** schema, so it must be `public` (not `gastos`, which `.env.example` shows).
- `RUN_MIGRATIONS=true` makes `app.py` execute `db/schema.sql` at startup. Failures are only logged as warnings.
- `init_pool()` failure exits the process.

## Architecture

Three layers, wired together in `app.py`:

- `models/<table>.py` — raw psycopg2 CRUD per table (`get_all`, `insert`, `update`, `delete`), returning lists of dicts. Each function opens a connection via `db.connection.get_connection()` (a `ThreadedConnectionPool` context manager) and commits itself.
- `transforms/*.py` — pure Polars/Plotly logic: converts model rows to display DataFrames (Spanish column names, money formatting via `utils/money.py`), and builds metrics and figures (`metricas.py`, `visualizaciones.py`, `resumen.py`).
- `ui/tab_*.py` — one module per Gradio tab, each exposing `build_tab()`. `app.py` assembles them in `gr.Tabs`. `tab_resumen_mes` no es una pestaña de primer nivel: `tab_tablas.build_tab()` la monta como sub-tab "Resumen del Mes" y devuelve `(fn, inputs, outputs, subtab)` para que `app.py` conecte `subtab.select`.

Tab refresh convention: `build_tab()` for tabs whose data can change elsewhere returns a refresh function plus its input/output components (e.g. `viz_fn, viz_inputs, viz_outputs`), and `app.py` wires it to `tab.select(...)`. When adding a tab with data from other tabs, follow this pattern rather than loading only at startup.

Shared constants (people, expense categories, responsible/type options) are in `utils/constants.py`.

## Gotchas

- `db/connection.py` registers a global psycopg2 type that converts `NUMERIC` to `float`. This is required: `Decimal` values are not JSON-serializable and a single one in any `gr.Dataframe` default makes Gradio fail to render the page.
- The expenses table is `gastos_variables`. A `categoria` redesign is in progress: a `categorias` table and `categoria_id` exist in the database but not in `db/schema.sql`, the old `categoria` text column is still the one written by the code, and about 69 rows still need manual reclassification. Check before changing category logic.
- `viajes` (trips) are an optional label on a gasto and do not affect its category.

## Contexto de negocio: presupuestos vs. gastos registrados

Algunos gastos fijos (p. ej. Supermercado) son en realidad **presupuestos**: se asigna un monto mensual (p. ej. 200 €) en `gastos_fijos`, con un responsable en `responsable_gastos`, pero el gasto real varía (p. ej. 150 €) y se **ingresa como gasto variable** en `gastos_variables`. El sobrante del presupuesto (50 €) debería ir a un fondo de ahorro.

Consecuencia para análisis y gráficos: en `gastos_variables`, `persona` es quien **registró/pagó** el gasto, no quien lo "pone" ni quien es responsable de él. No presentar lo registrado por cada uno como su aporte o su "peso" en el gasto total (ni escribir "Chiara pone el X %"). La asignación real de responsabilidad está en `responsable_gastos`. Al nombrar a ambas personas en textos de la UI usar «Marco y Chiara», no «la pareja».

### Dónde buscar si hay un bug con ahorros/fondos

- **El nombre de un ahorro es una clave de unión.** El monto de cada depósito se busca en `responsable_gastos` cruzando por **nombre** (`btrim(responsable_gastos.gasto) = btrim(ahorros.ahorro)`) y `responsable = persona`; no hay FK. Si se renombra un ahorro en *Gastos Fijos > Ahorros* sin renombrar a la vez su fila en *Responsable de Gastos* (o al revés), los depósitos nuevos se marcan **sin monto** (`pagos_ahorros.monto` NULL, aviso en el tracker) y el saldo del fondo queda corto. Lo mismo vale para los gastos fijos y su responsable. Una fila «Ambos» no sirve para el monto de un depósito: debe haber exactamente una fila por persona.
- **Casos de doble cuenta del saldo** (el saldo usa `updated_at` de `pagos_ahorros` y `created_at` de `gastos_variables` frente a `ahorros.fecha_corte`): un depósito marcado antes del corte, desmarcado y vuelto a marcar después cuenta otra vez; marcar después del corte un depósito que ya estaba en la cuenta cuando se cargó el saldo; registrar después del corte un retiro con fecha anterior al corte. Los excesos no se guardan: se recalculan en `models/fondos.py`.

## Pestañas y fuentes de datos

Estructura: `1️⃣ Ingresar Gasto`, `2️⃣ Panel de Control`, `3️⃣ Gastos Fijos` (sub-tabs: Gastos Fijos, Ingresos, Ahorros, Responsable de Gastos, Presupuestos, Resumen, Resumen del Mes), `4️⃣ Visualizaciones` (sub-tabs: General, Visualizaciones - por categoría), `5️⃣ Métricas`, `6️⃣ Viajes`, `7️⃣ Análisis de viajes`. La pestaña 4 tiene un bloque de filtros compartido sobre los sub-tabs (Persona Ambos/Marco/Chiara, Periodo con atajos Este mes / Últimos 3 meses / Todo, Tipo de gasto) que afecta a todos los gráficos; una sola función de refresco lee `gastos_variables` una vez (siempre ambas personas, desde el inicio de hace 2 meses) y alimenta ambos sub-tabs. Las comparaciones entre personas (lo registrado por cada una en €, mezcla de categorías) ignoran el filtro de Persona y lo indican en el gráfico; los textos hablan de «registrado», nunca de aporte, y la pestaña muestra una nota visible de que registrado no es aportado. Las tarjetas y títulos no usan porcentajes de participación ni comparaciones en puntos porcentuales. La lógica está en `transforms/visualizaciones.py`; el aviso de «Otros»/sin categoría usa la columna de texto `categoria`.

| Tabla | Quién la usa |
|---|---|
| `gastos_variables` | 1 (inserta, con `fondo_id` y `pagado_por` opcionales; tras guardar avisa el presupuesto de la categoría y, si es un retiro, el saldo/exceso del fondo); 2 (consumo por categoría vía `presupuestos.get_consumo_mes`); 3 > Resumen (gasto variable del mes, con `excluir_retiros=True`: los retiros de fondos no son gasto de caja); 4 > General (gasto mensual, registrado por persona); 4 > por categoría; 5; 6 y 7 (por `viaje_id`) |
| `presupuestos` | 3 > Presupuestos (CRUD con formulario y desplegables, no Dataframe editable); 2 (Panel de Control, lectura); 1 (aviso). **Depende de la migración `db/migrations/001_presupuestos.sql`**: hasta ejecutarla, las pestañas 2 y 3 > Presupuestos y el aviso de 1 muestran/loguean que la tabla no existe y el resto de la app funciona. Lógica pura en `transforms/presupuestos.py` (estado, proyección, HTML de tarjetas) |
| `gastos_fijos` | 3 > Gastos Fijos (CRUD); 3 > Resumen (total fijo); 3 > Resumen del Mes (lista de conceptos del tracker) |
| `pagos_fijos` | 3 > Resumen del Mes: tracker de pagos (CheckboxGroup Marco/Chiara + tabla ✅/⬜/N/A). Se crean filas del mes al abrir el sub-tab |
| `ahorros` | Cada fila es un **fondo**. 3 > Ahorros (edición POR ID con selector + guardar/eliminar, saldos de solo lectura y «Saldo actual del fondo» vía `ahorros.fijar_saldo_inicial`); 3 > Resumen del Mes (conceptos del tracker); 2 (tarjetas de Fondos); 1 (selector «Pagado con fondo») |
| `pagos_ahorros` | 3 > Resumen del Mes: tracker de depósitos (mismo patrón que pagos_fijos); `toggle_pago` guarda el `monto` del depósito y devuelve un `aviso` si queda sin monto (se muestra con `gr.Warning`) |
| `responsable_gastos` | 3 > Responsable de Gastos (CRUD); 3 > Resumen (reparto del fijo); 3 > Resumen del Mes: decide el "N/A" (cruce por nombre con `gastos_fijos.gasto` / `ahorros.ahorro`; si no hay fila, aplica a ambos) |
| `ingresos` | 3 > Ingresos (CRUD); 3 > Resumen (sobrante) |
| `viajes` | 6 (CRUD); 1 (selector); 7 |

Panel de Control: estado por presupuesto = excedido (> 100 %), a punto de excederse (≥ 80 % o proyección > tope) u OK; la proyección (ritmo actual) solo desde el día 4 del mes. El sobrante proyectado total (Σ max(tope − proyección, 0)) debería ir al fondo de ahorro.

Fondos de ahorro (lógica en `models/fondos.py`, presentación pura en `transforms/fondos.py`): saldo = `saldo_inicial` + depósitos marcados con `updated_at` > `fecha_corte` − retiros (gastos con `fondo_id`) con `created_at` > `fecha_corte`; sin corte cuenta todo y el saldo es aproximado («sin saldo de partida»). Un retiro es un gasto normal «Pagado con fondo»: sigue contando en los análisis por categoría, no consume presupuestos y no es gasto de caja del mes. `pagado_por` es quien pagó realmente (NULL = `persona`). El Panel de Control (2) agrega la sección Fondos (tarjetas con estado ✅ positivo / ⚠️ menos de un aporte mensual / 🔴 negativo) y el gráfico «¿Quién pagó el exceso?» (`models.fondos.get_excesos`); la sección de presupuestos y la de fondos fallan por separado. El exceso no descuenta reposiciones (no se registran). **Dependen de `db/migrations/002_fondos.sql`, que debe ejecutarse ANTES de desplegar (push a `main`)**: el código nuevo falla sin esas columnas.

Los trackers guardan solos al marcar (`CheckboxGroup.input`) y solo escriben las diferencias con `toggle_pago`. La lógica pura está en `transforms/tracker.py`. Los mapas de calor "Estado de Pagos/Depósitos del Mes" se retiraron de Visualizaciones.

## Subagentes y skills

- `.claude/agents/visualizaciones.md` (gráficos y UI de Gradio) y `.claude/agents/data-engineer.md` (depuración, refactors, rendimiento, validación e inserción). Las skills están en `.claude/skills/`; `supabase-conexion` documenta la conexión, el esquema real y las propuestas de mejora.
- Los agentes acceden a la base solo en lectura: todo es producción, no hay entorno de test.

## Idioma

Comentarios, documentación y textos de usuario van en español.
