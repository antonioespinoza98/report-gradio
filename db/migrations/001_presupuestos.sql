-- ============================================================
-- MIGRACIÓN 001: presupuestos
-- ------------------------------------------------------------
-- Un presupuesto es un tope mensual que se consume con los gastos
-- de gastos_variables de la misma categoría (columna de texto
-- gastos_variables.categoria). Esta migración:
--   1. Crea la tabla presupuestos (si no existe).
--   2. Carga los 4 presupuestos iniciales con los valores dados
--      por el usuario.
--
-- No toca gastos_fijos, responsable_gastos ni pagos_fijos: en la
-- lectura de solo lectura del 2026-10-25 ninguno de los conceptos
-- (incluido «Viajecitos», que no se migra) existe en esas tablas,
-- así que no hay nada que mover, respaldar ni borrar.
--
-- Ejecutar UNA vez, completo, en el SQL Editor de Supabase o con
-- psql -v ON_ERROR_STOP=1 -f db/migrations/001_presupuestos.sql
-- Es idempotente: re-ejecutarlo no duplica ni pisa montos ya
-- existentes (ON CONFLICT (nombre) DO NOTHING).
-- ============================================================

BEGIN;

-- ------------------------------------------------------------
-- 1. Tabla presupuestos (misma definición que en db/schema.sql)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS presupuestos (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(200)    NOT NULL UNIQUE,
    categoria       VARCHAR(50)     NOT NULL,
    monto_mensual   NUMERIC(12, 2)  NOT NULL CHECK (monto_mensual >= 0),
    responsable     VARCHAR(50)     NOT NULL CHECK (responsable IN ('Marco', 'Chiara', 'Ambos'))
);

-- ------------------------------------------------------------
-- 2. Presupuestos iniciales.
--    categoria = mismo texto que utils/constants.py CATEGORIAS y
--    que gastos_variables.categoria (verificado el 2026-10-25).
--    Si un nombre ya existe, se deja como está (no se pisa el
--    monto que se haya editado desde la UI).
-- ------------------------------------------------------------
INSERT INTO presupuestos (nombre, categoria, monto_mensual, responsable) VALUES
    ('Alcohol, Tabaco & Weed', 'Alcohol, Tabaco & Weed',  50.00, 'Marco'),
    ('Entretenimiento',        'Entretenimiento',         50.00, 'Chiara'),
    ('Restaurante',            'Restaurante',            100.00, 'Chiara'),
    ('Supermercado',           'Supermercado',           400.00, 'Chiara')
ON CONFLICT (nombre) DO NOTHING;

-- ------------------------------------------------------------
-- (OPCIONAL) RLS. Depende de tu configuración de Supabase: si la
-- API REST está expuesta con la clave anónima, habilitarlo evita
-- que la tabla sea legible/escribible por esa vía. Sin políticas,
-- solo el dueño de la tabla (el rol de DATABASE_URL, que es quien
-- la crea) sigue accediendo, así que la app no se ve afectada.
-- No se activa por defecto:
-- ALTER TABLE presupuestos ENABLE ROW LEVEL SECURITY;
-- ------------------------------------------------------------

COMMIT;

-- ============================================================
-- VERIFICACIÓN (ejecutar después, son solo SELECT)
-- ============================================================
-- Presupuestos cargados (deben ser 4 filas con estos valores):
-- SELECT id, nombre, categoria, monto_mensual, responsable FROM presupuestos ORDER BY nombre;
--
-- Total de topes (debe dar 600.00):
-- SELECT SUM(monto_mensual) FROM presupuestos;
--
-- Cada categoría de presupuesto existe en gastos_variables (debe dar 0 filas):
-- SELECT p.nombre, p.categoria FROM presupuestos p
-- WHERE NOT EXISTS (SELECT 1 FROM gastos_variables g WHERE g.categoria = p.categoria);
--
-- ============================================================
-- REVERSIÓN (ejecutar a mano; borra la tabla y sus datos)
-- ============================================================
-- DROP TABLE presupuestos;
