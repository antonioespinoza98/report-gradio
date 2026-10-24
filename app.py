import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr
from dotenv import load_dotenv
from db.connection import init_pool, execute_sql_file
from ui import (tab_ingresar_gasto, tab_tablas, tab_visualizaciones,
                tab_visualizaciones_categoria, tab_metricas, tab_viajes,
                tab_viajes_analisis)

# Load environment variables
load_dotenv()

# Initialize database connection pool
try:
    init_pool()
    print("✅ Database connection pool initialized")
except Exception as e:
    print(f"❌ Failed to initialize database: {e}")
    sys.exit(1)

# Run migrations if needed
try:
    run_migrations = os.getenv("RUN_MIGRATIONS", "false").lower() == "true"
    if run_migrations:
        schema_path = Path(__file__).parent / "db" / "schema.sql"
        execute_sql_file(str(schema_path))
        print("✅ Schema migrations completed")
except Exception as e:
    print(f"⚠️  Migration warning: {e}")

# Build Gradio app
def build_app():
    """Build the main Gradio interface."""
    with gr.Blocks(title="Report Gradio - Gestor de Gastos") as demo:
        gr.Markdown("# 💸 Report Gradio\nApp para gestionar gastos compartidos entre Marco y Chiara")

        with gr.Tabs():
            # Tab 1: Ingresar Gasto — refresh viajes dropdown on select so
            # trips created in the Viajes tab appear without a reload
            with gr.Tab(label="1️⃣ Ingresar Gasto", id="tab_ingresar_gasto") as tab1:
                gasto_viajes_fn, gasto_viaje_dd = tab_ingresar_gasto.build_tab()
            tab1.select(fn=gasto_viajes_fn, inputs=[], outputs=[gasto_viaje_dd])

            # Tab 2: Gastos Fijos — el sub-tab "Resumen del Mes" (trackers de pagos y
            # ahorros) se refresca al seleccionarlo, para ver gastos fijos nuevos.
            # Se conecta solo al sub-tab (no al padre) para no leer/escribir dos veces.
            with gr.Tab(label="2️⃣ Gastos Fijos", id="tab_gastos_fijos"):
                resumen_fn, resumen_inputs, resumen_outputs, subtab_resumen = tab_tablas.build_tab()
            subtab_resumen.select(fn=resumen_fn, inputs=resumen_inputs, outputs=resumen_outputs)

            # Tab 3: Visualizaciones — auto-refresh on select
            with gr.Tab(label="3️⃣ Visualizaciones", id="tab_visualizaciones") as tab3:
                viz_fn, viz_inputs, viz_outputs = tab_visualizaciones.build_tab()
            tab3.select(fn=viz_fn, inputs=viz_inputs, outputs=viz_outputs)

            # Tab 4: Visualizaciones por categoría — auto-refresh on select
            with gr.Tab(label="4️⃣ Visualizaciones - por categoría", id="tab_visualizaciones_categoria") as tab4:
                cat_fn, cat_inputs, cat_outputs = tab_visualizaciones_categoria.build_tab()
            tab4.select(fn=cat_fn, inputs=cat_inputs, outputs=cat_outputs)

            # Tab 5: Métricas — auto-refresh on select
            with gr.Tab(label="5️⃣ Métricas", id="tab_metricas") as tab5:
                met_fn, met_inputs, met_outputs = tab_metricas.build_tab()
            tab5.select(fn=met_fn, inputs=met_inputs, outputs=met_outputs)

            # Tab 6: Viajes — auto-refresh on select
            with gr.Tab(label="6️⃣ Viajes", id="tab_viajes") as tab6:
                viajes_fn, viajes_tbl = tab_viajes.build_tab()
            tab6.select(fn=viajes_fn, inputs=[], outputs=[viajes_tbl])

            # Tab 7: Análisis de viajes — auto-refresh on select
            with gr.Tab(label="7️⃣ Análisis de viajes", id="tab_viajes_analisis") as tab7:
                via_fn, via_inputs, via_outputs = tab_viajes_analisis.build_tab()
            tab7.select(fn=via_fn, inputs=via_inputs, outputs=via_outputs)

    return demo

if __name__ == "__main__":
    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False
    )
