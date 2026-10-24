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

## Pestañas y fuentes de datos

Estructura: `1️⃣ Ingresar Gasto`, `2️⃣ Gastos Fijos` (sub-tabs: Gastos Fijos, Ingresos, Ahorros, Responsable de Gastos, Resumen, Resumen del Mes), `3️⃣ Visualizaciones`, `4️⃣ Visualizaciones - por categoría`, `5️⃣ Métricas`, `6️⃣ Viajes`, `7️⃣ Análisis de viajes`.

| Tabla | Quién la usa |
|---|---|
| `gastos_variables` | 1 (inserta); 2 > Resumen (gasto variable del mes); 3 (Gastos en el Tiempo, Comparativa); 4; 5; 6 y 7 (por `viaje_id`) |
| `gastos_fijos` | 2 > Gastos Fijos (CRUD); 2 > Resumen (total fijo); 2 > Resumen del Mes (lista de conceptos del tracker) |
| `pagos_fijos` | 2 > Resumen del Mes: tracker de pagos (CheckboxGroup Marco/Chiara + tabla ✅/⬜/N/A). Se crean filas del mes al abrir el sub-tab |
| `ahorros` | 2 > Ahorros (CRUD); 2 > Resumen del Mes (conceptos del tracker de depósitos) |
| `pagos_ahorros` | 2 > Resumen del Mes: tracker de depósitos (mismo patrón que pagos_fijos) |
| `responsable_gastos` | 2 > Responsable de Gastos (CRUD); 2 > Resumen (reparto del fijo); 2 > Resumen del Mes: decide el "N/A" (cruce por nombre con `gastos_fijos.gasto` / `ahorros.ahorro`; si no hay fila, aplica a ambos) |
| `ingresos` | 2 > Ingresos (CRUD); 2 > Resumen (sobrante) |
| `viajes` | 6 (CRUD); 1 (selector); 7 |

Los trackers guardan solos al marcar (`CheckboxGroup.input`) y solo escriben las diferencias con `toggle_pago`. La lógica pura está en `transforms/tracker.py`. Los mapas de calor "Estado de Pagos/Depósitos del Mes" se retiraron de Visualizaciones.

## Subagentes y skills

- `.claude/agents/visualizaciones.md` (gráficos y UI de Gradio) y `.claude/agents/data-engineer.md` (depuración, refactors, rendimiento, validación e inserción). Las skills están en `.claude/skills/`; `supabase-conexion` documenta la conexión, el esquema real y las propuestas de mejora.
- Los agentes acceden a la base solo en lectura: todo es producción, no hay entorno de test.

## Idioma

Comentarios, documentación y textos de usuario van en español.
