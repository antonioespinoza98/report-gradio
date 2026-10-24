---
name: supabase-conexion
description: Cómo se conecta este proyecto a la base Postgres (Supabase), esquema real de tablas, tipos, convenciones de montos en euros y propuestas de mejora. Usalo antes de escribir cualquier consulta, modelo, transformación o gráfico que toque datos. Acceso de SOLO LECTURA para los agentes.
---

# Conexión a Supabase y esquema

> Todo es producción: no hay entorno de test. Los agentes **solo leen** la base. Cualquier INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER o migración se escribe como SQL propuesto y lo ejecuta el usuario.

## Método de conexión (verificado en el código)

- Cliente: **psycopg2** (`psycopg2-binary`) directo contra Postgres. No se usa supabase-py, ni SQLAlchemy, ni `polars.read_database`.
- `db/connection.py`: `init_pool()` crea un `ThreadedConnectionPool(1, 20, DATABASE_URL, options="-c search_path=<DB_SCHEMA>")`. `get_connection()` es un context manager que devuelve la conexión al pool.
- Cada función de `models/*.py` abre conexión, ejecuta SQL parametrizado (`%s`), hace `commit()` y devuelve `list[dict]`. Las transformaciones (`transforms/*.py`) convierten esas filas a `pl.DataFrame`.
- `app.py` llama `load_dotenv()` e `init_pool()` al arrancar; si falla, el proceso termina.
- Registro global de tipo: `NUMERIC` se lee como `float` (no `Decimal`) porque Gradio no serializa `Decimal` a JSON.

### Variables de entorno (solo nombres)

- `DATABASE_URL` — cadena de conexión Postgres.
- `DB_SCHEMA` — `search_path`; debe ser `public` (las tablas viven en `public`, aunque `.env.example` muestre `gastos`).
- `RUN_MIGRATIONS` — si es `true`, `app.py` ejecuta `db/schema.sql` al iniciar.

`.env` está en `.gitignore` y no está versionado (solo `.env.example`). Nunca imprimas, registres ni copies valores de `.env`.

### Cómo leer la base desde un agente

Script de una sola vez, sesión de solo lectura, sin imprimir credenciales:

```python
# .venv/bin/python -I script.py
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv(".env")
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.set_session(readonly=True)   # la sesión rechaza cualquier escritura
cur = conn.cursor()
cur.execute("SELECT categoria, SUM(monto) FROM gastos_variables GROUP BY 1 LIMIT 50")
```

Reglas: siempre `readonly=True`, siempre `LIMIT` al explorar, parámetros con `%s` (nunca f-strings con valores), no volcar filas completas de la tabla.

## Esquema real (consultado en `information_schema`, 2026-10-24)

| Tabla | Columnas (tipo) | Notas |
|---|---|---|
| `gastos_variables` | `id` serial PK, `persona` varchar(50), `descripcion` text, `categoria` varchar(50), `monto` numeric(12,2), `fecha` date, `created_at` timestamptz, `tipo_de_gasto` varchar(50), `categoria_id` int NULL → `categorias.id`, `viaje_id` int NULL → `viajes.id`, `otros_nota` text NULL | CHECK `monto > 0`; `persona` ∈ {Marco, Chiara}; `tipo_de_gasto` ∈ {Gasto Común, Gasto Personal}. Índices: persona, fecha, categoria, categoria_id, viaje_id. ~577 filas (2026-04-01 → 2026-10-24) |
| `categorias` | `id` PK, `nombre` varchar UNIQUE | Valores: Supermercado, Restaurante, Transporte, Entretenimiento, Bebidas y Tabaco, Salud, Viajecitos, Deporte, Subscripciones, Ropa, Otros |
| `viajes` | `id`, `nombre`, `destino` NULL, `fecha_inicio` date, `fecha_fin` date, `created_at` | CHECK `fecha_fin >= fecha_inicio`. Es una etiqueta; no cambia la categoría |
| `gastos_fijos` | `id`, `gasto` UNIQUE, `total` numeric(12,2) | CHECK `total >= 0` |
| `ingresos` | `id`, `tipo_ingreso`, `total` numeric(12,2), `persona` | |
| `ahorros` | `id`, `ahorro` UNIQUE, `total` numeric(12,2) | |
| `responsable_gastos` | `id`, `gasto`, `responsable` ∈ {Marco, Chiara, Ambos}, `monto` numeric(12,2) | |
| `pagos_fijos` | `id`, `gasto_fijo_id` FK CASCADE, `persona`, `mes` smallint 1-12, `anio` smallint ≥2020, `pagado` bool, `updated_at` | UNIQUE (gasto_fijo_id, persona, mes, anio) |
| `pagos_ahorros` | `id`, `ahorro_id` FK CASCADE, `persona`, `mes`, `anio`, `pagado`, `updated_at` | UNIQUE (ahorro_id, persona, mes, anio) |

### Deriva entre `db/schema.sql` y la base real

`schema.sql` **no** define `categorias`, `categoria_id` ni `otros_nota`: existen en la base pero no en las migraciones del repo. Además `utils/constants.py` usa "Alcohol, Tabaco & Weed" y la tabla `categorias` dice "Bebidas y Tabaco". Antes de agrupar por categoría, verificá cuál columna usás (`categoria` texto vs. `categoria_id`): de 577 filas, 234 tienen `categoria_id` NULL, y `models/gastos.py` no escribe `categoria_id` ni `otros_nota`.

## Convenciones de montos (euros)

- La base guarda `numeric(12,2)`: exacto, sin riesgo de redondeo en el almacenamiento.
- **Riesgo actual**: el código convierte a `float` al insertar (`float(data["monto"])`) y al leer (adaptador global `DEC2FLOAT`). Sumar floats puede dar `1234.5600000000002`; por eso `utils/money.py::money()` redondea a 2 decimales después de agregar.
- Regla para código nuevo: **`Decimal` o enteros en céntimos, nunca `float`** para guardar o validar montos. Cuando un dato debe pasar a Gradio/Plotly (que necesitan float), convertí al final, justo antes de mostrar, y redondeá con `money()`.
- Moneda única: euros. Formato de salida en español: `1.234,56 €` (ver skill `eleccion-de-graficos`).
- Sumas en SQL (`SUM(monto)`) son exactas en `numeric`; preferilas a sumar floats en Python cuando se pueda.

## Propuestas de mejora (no aplicadas)

Seguridad
1. Crear un rol Postgres de solo lectura (`GRANT SELECT`) para los agentes/análisis, con su propia URL, y dejar el rol con escritura solo para la app. Hoy `DATABASE_URL` tiene permisos de escritura y la regla "solo lectura" depende de la disciplina (`set_session(readonly=True)`).
2. Activar RLS en Supabase o confirmar que las tablas de `public` no quedan expuestas por la API REST con la clave anónima.
3. Rotar la contraseña si alguna vez se imprimió la URL en logs.

Integridad de datos
4. Insertar `monto` como `Decimal` (`Decimal(str(monto))`) en lugar de `float(...)`.
5. Validar antes de insertar: `monto > 0` (hoy, con monto 0, la CHECK de la base falla con un error crudo), `descripcion` no vacía tras `strip()`, `fecha` válida y no absurda, categoría existente.
6. Bug en `ui/tab_ingresar_gasto.py::on_save_click`: `gr.Error(...)` se instancia pero no se lanza (`raise`), y el `except` devuelve `None` en todas las salidas, borrando el formulario sin avisar. Debe usar `raise gr.Error(...)`.
7. Sincronizar `db/schema.sql` con la base real (`categorias`, `categoria_id`, `otros_nota`) y alinear `utils/constants.py::CATEGORIAS` con `categorias.nombre`, idealmente leyéndolas de la base.
8. Detección de duplicados al insertar (misma persona, fecha, monto y descripción); hoy no hay ninguno repetido, pero nada lo impide.

Rendimiento
9. Pooling: `ThreadedConnectionPool(1, 20)` directo. Si la URL es la de conexión directa de Supabase, usar el pooler (puerto 6543, modo transaction) y bajar `maxconn`; 20 conexiones pueden agotar el límite del plan gratuito.
10. `get_all()` trae toda la tabla en cada selección de pestaña. Con crecimiento, filtrar por rango de fechas en SQL o agregar por periodo en SQL (`date_trunc`).
11. Índice compuesto `(fecha, categoria_id)` si las consultas por categoría y periodo se vuelven lentas; hoy los índices simples alcanzan con ~600 filas.
12. `requirements.txt` no lista `gradio` (lo instala el Space según `sdk_version: 5.25.0` del README) y el entorno local usa 6.25.0: fijar versiones para evitar diferencias entre local y producción.
