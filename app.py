import os
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import gradio as gr
from dotenv import load_dotenv
from db.connection import init_pool, execute_sql_file
from ui import tab_ingresar_gasto, tab_tablas, tab_resumen_mes, tab_visualizaciones, tab_viajes

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

            # Tab 2: Tablas Predeterminadas
            with gr.Tab(label="2️⃣ Tablas Predeterminadas", id="tab_tablas"):
                tab_tablas.build_tab()

            # Tab 3: Resumen del Mes — auto-refresh on select so new gastos_fijos appear
            with gr.Tab(label="3️⃣ Resumen del Mes", id="tab_resumen_mes") as tab3:
                resumen_fn, mes_i, anio_i, pmt_table, ahorros_tbl = tab_resumen_mes.build_tab()
            tab3.select(fn=resumen_fn, inputs=[mes_i, anio_i], outputs=[pmt_table, ahorros_tbl])

            # Tab 4: Visualizaciones — auto-refresh on select
            with gr.Tab(label="4️⃣ Visualizaciones", id="tab_visualizaciones") as tab4:
                viz_fn, viz_inputs, viz_outputs = tab_visualizaciones.build_tab()
            tab4.select(fn=viz_fn, inputs=viz_inputs, outputs=viz_outputs)

            # Tab 5: Viajes — auto-refresh on select
            with gr.Tab(label="5️⃣ Viajes", id="tab_viajes") as tab5:
                viajes_fn, viajes_tbl = tab_viajes.build_tab()
            tab5.select(fn=viajes_fn, inputs=[], outputs=[viajes_tbl])

    return demo

if __name__ == "__main__":
    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True,
        share=False
    )
