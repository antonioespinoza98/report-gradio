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
- `ui/tab_*.py` — one module per Gradio tab, each exposing `build_tab()`. `app.py` assembles them in `gr.Tabs`.

Tab refresh convention: `build_tab()` for tabs whose data can change elsewhere returns a refresh function plus its input/output components (e.g. `viz_fn, viz_inputs, viz_outputs`), and `app.py` wires it to `tab.select(...)`. When adding a tab with data from other tabs, follow this pattern rather than loading only at startup.

Shared constants (people, expense categories, responsible/type options) are in `utils/constants.py`.

## Gotchas

- `db/connection.py` registers a global psycopg2 type that converts `NUMERIC` to `float`. This is required: `Decimal` values are not JSON-serializable and a single one in any `gr.Dataframe` default makes Gradio fail to render the page.
- The expenses table is `gastos_variables`. A `categoria` redesign is in progress: a `categorias` table and `categoria_id` exist in the database but not in `db/schema.sql`, the old `categoria` text column is still the one written by the code, and about 69 rows still need manual reclassification. Check before changing category logic.
- `viajes` (trips) are an optional label on a gasto and do not affect its category.

## Subagentes y skills

- `.claude/agents/visualizaciones.md` (gráficos y UI de Gradio) y `.claude/agents/data-engineer.md` (depuración, refactors, rendimiento, validación e inserción). Las skills están en `.claude/skills/`; `supabase-conexion` documenta la conexión, el esquema real y las propuestas de mejora.
- Los agentes acceden a la base solo en lectura: todo es producción, no hay entorno de test.

## Idioma

Comentarios, documentación y textos de usuario van en español.
