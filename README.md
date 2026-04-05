---
title: Report Gradio
emoji: 💸
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "4.44.0"
app_file: app.py
pinned: false
---

# Report Gradio

App interactiva para registrar y visualizar gastos compartidos entre Marco y Chiara.

## Características

- **Ingresar Gasto**: Formulario interactivo para registrar gastos variables
- **Tablas Predeterminadas**: Gestión de gastos fijos, ingresos, ahorros y responsables
- **Resumen Mensual**: Tracking interactivo de pagos de gastos fijos
- **Visualizaciones**: Gráficos de gastos por categoría, persona, y comparativas

## Despliegue

1. Clonar el repositorio
2. Crear `.env` basado en `.env.example` con credenciales PostgreSQL
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar: `python app.py`

## Tech Stack

- **Backend**: Python + Gradio
- **Database**: PostgreSQL
- **Data**: Polars (transformaciones)
- **Visualizaciones**: Plotly