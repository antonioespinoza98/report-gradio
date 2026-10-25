---
title: Report Gradio
emoji: 💸
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: "6.25.0"
app_file: app.py
pinned: false
---

# Report Gradio

App interactiva para registrar y visualizar gastos compartidos entre Marco y Chiara.

## Características

- **Ingresar Gasto**: Formulario interactivo para registrar gastos variables
- **Panel de Control**: estado de los presupuestos del mes (gastado vs. tope, proyección a fin de mes y sobrante)
- **Fondos de ahorro**: cada ahorro es un fondo con saldo; los gastos se pueden pagar con un fondo y el Panel de Control muestra saldos y quién pagó los excesos
- **Gastos Fijos**: gestión de gastos fijos, ingresos, ahorros, responsables y presupuestos, resumen y seguimiento mensual de pagos/depósitos
- **Visualizaciones**: filtros compartidos (persona, periodo, tipo de gasto) y sub-tabs General (gasto mensual, lo registrado por Marco y por Chiara) y por categoría

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
