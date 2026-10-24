---
name: python-buenas-practicas
description: Tipado, estructura de módulos, manejo de errores, tests con pytest y linter/formatter (ruff) siguiendo las convenciones existentes de este proyecto. Usalo al refactorizar, depurar o agregar lógica Python (modelos, validación, inserción).
---

# Buenas prácticas de Python en este proyecto

## Convenciones existentes (respetarlas)

- Capas: `models/` (SQL con psycopg2, devuelve `list[dict]`), `transforms/` (Polars/Plotly puro), `ui/` (Gradio), `utils/` (constantes y helpers). Las dependencias van en una sola dirección: ui → transforms/models → db.
- Cada función de `models/` abre su conexión con `get_connection()`, usa parámetros `%s` y hace `commit()`.
- Sin clases salvo necesidad; funciones con docstring corto. **Comentarios, docstrings y textos de usuario en español.**
- Anotaciones modernas ya usadas: `list[dict]`, `date | None`.

## Reglas

1. **Tipado**: anotá parámetros y retornos en código nuevo o tocado (`def insert(data: dict) -> dict:`). Preferí `TypedDict` o `dataclass` para el gasto antes que `dict` suelto si agregás validación.
2. **Validación en un solo lugar**: una función pura (p. ej. `validar_gasto(...) -> GastoValidado`) que normalice y verifique antes de llegar a `models.gastos.insert`: `monto` como `Decimal` > 0 con 2 decimales, `descripcion` no vacía, `fecha` válida, `persona`/`categoria`/`tipo_de_gasto` dentro de las listas permitidas. Debe poder probarse sin base de datos.
3. **Montos**: `Decimal(str(valor))` y `quantize(Decimal("0.01"))`; nunca `float` para guardar. psycopg2 adapta `Decimal` a `numeric` directamente.
4. **Errores**: capturá excepciones específicas (`psycopg2.errors.CheckViolation`, `ValueError`), no `except Exception` mudo. En `ui/` traducilas a `raise gr.Error("mensaje claro en español")`. No tragues errores devolviendo listas vacías sin avisar si afecta lo que ve el usuario.
5. **Transacciones**: si hacés varias escrituras relacionadas, un solo `commit()`; ante excepción `conn.rollback()`.
6. **Sin secretos** en código ni logs; `print` de estado sin URLs ni credenciales.
7. **Cambios mínimos**: no reformatees archivos enteros ajenos a la tarea.

## Tests (pytest)

No existe suite todavía. Al crear la primera:

- Carpeta `tests/`, archivos `test_<modulo>.py`. Agregar `pytest` a un `requirements-dev.txt` (no a `requirements.txt`, que usa el Space).
- Probar funciones puras: `validar_gasto`, `transforms/*` (con listas de dicts en memoria), `money()`.
- **Nunca** conectar a la base real desde tests: no hay entorno de test y todo es producción. Para `models/`, usar dobles (monkeypatch de `get_connection`) o limitarse a probar el SQL con `cur.mogrify` sin ejecutar.
- Ejemplo:

```python
from decimal import Decimal
import polars as pl
from utils.money import money

def test_money_redondea_a_centimos():
    df = pl.DataFrame({"m": [0.1, 0.2, 1234.56]}).select(money(pl.col("m").sum()))
    assert df.item() == 1234.86

def test_validar_monto_cero_falla():
    import pytest
    with pytest.raises(ValueError):
        validar_gasto(monto=Decimal("0"), ...)
```

Ejecutar: `.venv/bin/python -m pytest -q`; un solo test: `.venv/bin/python -m pytest tests/test_x.py::test_nombre -q`.

## Linter y formatter

Recomendado `ruff` (hoy no está configurado ni instalado: proponelo, no lo impongas). Ejecutar `ruff check .` y `ruff format --check <archivos tocados>`. Si no está instalado, decíselo al usuario y usá `python -m py_compile <archivo>` como verificación mínima.

## Después de un cambio relevante

Compilar (`python -m py_compile`), correr tests si existen, correr el linter si está, y arrancar `python app.py` para ver que la app levanta.
