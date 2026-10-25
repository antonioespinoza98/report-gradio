-- ============================================================
-- MIGRACIÓN 002: fondos de ahorro con saldo
-- ------------------------------------------------------------
-- Cada fila de `ahorros` pasa a ser un FONDO con saldo:
--
--   saldo = saldo_inicial
--         + depósitos marcados (pagos_ahorros.pagado) DESPUÉS del corte
--         − retiros (gastos_variables con fondo_id) registrados DESPUÉS del corte
--
-- «Después del corte» = pagos_ahorros.updated_at > ahorros.fecha_corte
-- para depósitos y gastos_variables.created_at > ahorros.fecha_corte
-- para retiros. Si fecha_corte es NULL (aún no se cargó el saldo de
-- partida desde la UI) cuentan todos los depósitos y retiros.
--
-- Esta migración:
--   1. pagos_ahorros: agrega `monto` (cuánto se depositó) y lo rellena
--      SOLO en las filas ya marcadas (pagado = TRUE) con el monto
--      actual de responsable_gastos (aprobado por el usuario).
--   2. ahorros: agrega `saldo_inicial` (DEFAULT 0) y `fecha_corte`
--      (NULL hasta que se cargue el saldo desde la UI).
--   3. gastos_variables: agrega `fondo_id` («Pagado con fondo», FK a
--      ahorros, ON DELETE SET NULL), `pagado_por` (Marco/Chiara; NULL
--      en filas viejas = quien lo registró, `persona`) e índice en
--      fondo_id.
--
-- Todas las columnas nuevas son NULL o tienen DEFAULT constante, así
-- que el código actual (sin estas columnas) sigue funcionando después
-- de ejecutarla. El código NUEVO, en cambio, falla sin ella: ejecutar
-- esta migración ANTES de desplegar (push a main).
--
-- Bloqueos: cada ALTER TABLE toma ACCESS EXCLUSIVE sobre su tabla hasta
-- el COMMIT. ADD COLUMN con NULL o DEFAULT constante es solo de
-- metadatos (no reescribe la tabla, Postgres >= 11; la base es 17).
-- Validar los CHECK/FK nuevos recorre la tabla (~580 filas en
-- gastos_variables, todas con la columna nueva en NULL): milisegundos.
-- La FK toma además SHARE ROW EXCLUSIVE sobre ahorros. CREATE INDEX
-- (no CONCURRENTLY, que no puede ir dentro de BEGIN) bloquea escrituras
-- en gastos_variables mientras se construye: milisegundos con ~580
-- filas. lock_timeout evita quedarse en cola detrás de una transacción
-- abierta de la app (y bloquear a su vez a todas las consultas que
-- lleguen detrás): si salta, no se aplica nada; reintentar.
--
-- Ejecutar UNA vez, completo, en el SQL Editor de Supabase o con
-- psql -v ON_ERROR_STOP=1 -f db/migrations/002_fondos.sql
-- Es idempotente: re-ejecutarla no duplica columnas ni restricciones,
-- y el relleno solo toca filas con monto NULL.
-- ============================================================

BEGIN;

SET LOCAL lock_timeout = '5s';

-- ------------------------------------------------------------
-- 1. pagos_ahorros.monto: cuánto se depositó al marcar.
--    NULL = no marcado, o marcado sin monto conocido.
-- ------------------------------------------------------------
ALTER TABLE pagos_ahorros ADD COLUMN IF NOT EXISTS monto NUMERIC(12, 2);
DO $$ BEGIN
    ALTER TABLE pagos_ahorros ADD CONSTRAINT pagos_ahorros_monto_check CHECK (monto >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Relleno: solo filas marcadas (pagado = TRUE) y aún sin monto. El
-- monto sale de responsable_gastos con gasto = nombre del ahorro
-- (mismo cruce por nombre, sin espacios sobrantes, que usa el tracker)
-- y responsable = persona. Si para esa pareja hay 0 filas (o solo una
-- fila «Ambos») o varias filas, se deja NULL y se avisa abajo.
-- No toca updated_at: es la marca de tiempo que decide si el depósito
-- cuenta después del corte.
-- Esperado al 2026-10-25 (lectura de solo lectura): 14 filas rellenadas,
-- 0 sin monto.
DO $$
DECLARE
    n_rellenadas INTEGER;
    n_sin_monto  INTEGER;
BEGIN
    WITH montos AS (
        SELECT a.id AS ahorro_id, r.responsable AS persona,
               MIN(r.monto) AS monto, COUNT(*) AS n
        FROM ahorros a
        JOIN responsable_gastos r ON btrim(r.gasto) = btrim(a.ahorro)
        WHERE r.responsable IN ('Marco', 'Chiara')
        GROUP BY a.id, r.responsable
    )
    UPDATE pagos_ahorros p
    SET monto = m.monto
    FROM montos m
    WHERE p.ahorro_id = m.ahorro_id
      AND p.persona   = m.persona
      AND m.n = 1
      AND p.pagado
      AND p.monto IS NULL;
    GET DIAGNOSTICS n_rellenadas = ROW_COUNT;

    SELECT COUNT(*) INTO n_sin_monto
    FROM pagos_ahorros
    WHERE pagado AND monto IS NULL;

    RAISE NOTICE 'pagos_ahorros: % filas marcadas rellenadas con monto.', n_rellenadas;
    IF n_sin_monto > 0 THEN
        RAISE NOTICE 'pagos_ahorros: % filas marcadas quedaron SIN monto (0 o varias filas en responsable_gastos). Ver la consulta de revisión al final.', n_sin_monto;
    END IF;
END $$;

-- ------------------------------------------------------------
-- 2. ahorros: saldo de partida y fecha/hora de corte.
--    saldo_inicial >= 0: es dinero real que hay en el fondo al cargarlo.
--    Un fondo puede quedar en negativo DESPUÉS (retiros que exceden),
--    pero eso se calcula, no se guarda aquí.
-- ------------------------------------------------------------
ALTER TABLE ahorros ADD COLUMN IF NOT EXISTS saldo_inicial NUMERIC(12, 2) NOT NULL DEFAULT 0;
DO $$ BEGIN
    ALTER TABLE ahorros ADD CONSTRAINT ahorros_saldo_inicial_check CHECK (saldo_inicial >= 0);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE ahorros ADD COLUMN IF NOT EXISTS fecha_corte TIMESTAMPTZ;

-- ------------------------------------------------------------
-- 3. gastos_variables: fondo con el que se pagó y quién pagó.
--    fondo_id NULL = gasto normal de caja. ON DELETE SET NULL: si se
--    borra un fondo, sus retiros siguen existiendo como gastos normales
--    (vuelven a contar en presupuestos y en la caja del mes).
--    pagado_por NULL = lo pagó quien lo registró (persona).
-- ------------------------------------------------------------
ALTER TABLE gastos_variables ADD COLUMN IF NOT EXISTS fondo_id INTEGER;
DO $$ BEGIN
    ALTER TABLE gastos_variables ADD CONSTRAINT gastos_variables_fondo_id_fkey
        FOREIGN KEY (fondo_id) REFERENCES ahorros(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE gastos_variables ADD COLUMN IF NOT EXISTS pagado_por VARCHAR(50);
DO $$ BEGIN
    ALTER TABLE gastos_variables ADD CONSTRAINT gastos_variables_pagado_por_check
        CHECK (pagado_por IN ('Marco', 'Chiara'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_gastos_variables_fondo_id ON gastos_variables (fondo_id);

-- ------------------------------------------------------------
-- (OPCIONAL, no se aplica) Coherencia marcado/monto: impediría que
-- quede un monto en una fila desmarcada. El código ya lo garantiza
-- (toggle_pago pone NULL al desmarcar):
-- ALTER TABLE pagos_ahorros ADD CONSTRAINT pagos_ahorros_monto_si_pagado
--     CHECK (pagado OR monto IS NULL);
-- ------------------------------------------------------------

COMMIT;

-- ============================================================
-- VERIFICACIÓN (ejecutar después, son solo SELECT)
-- ============================================================
-- Columnas nuevas (deben salir 5 filas):
-- SELECT table_name, column_name, data_type, numeric_precision, numeric_scale,
--        character_maximum_length, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND (table_name, column_name) IN (('pagos_ahorros', 'monto'),
--        ('ahorros', 'saldo_inicial'), ('ahorros', 'fecha_corte'),
--        ('gastos_variables', 'fondo_id'), ('gastos_variables', 'pagado_por'))
-- ORDER BY 1, 2;
--
-- Restricciones e índice nuevos (deben salir 4 + 1 filas):
-- SELECT conname, conrelid::regclass, pg_get_constraintdef(oid)
-- FROM pg_constraint
-- WHERE conname IN ('pagos_ahorros_monto_check', 'ahorros_saldo_inicial_check',
--                   'gastos_variables_fondo_id_fkey', 'gastos_variables_pagado_por_check');
-- SELECT indexname FROM pg_indexes WHERE indexname = 'idx_gastos_variables_fondo_id';
--
-- Relleno (esperado: 14 con monto, 0 sin monto; desmarcadas todas sin monto):
-- SELECT pagado, monto IS NOT NULL AS con_monto, COUNT(*)
-- FROM pagos_ahorros GROUP BY 1, 2 ORDER BY 1, 2;
--
-- Revisión: filas marcadas sin monto y por qué (n_resp = filas en responsable_gastos):
-- SELECT p.id, a.ahorro, p.persona, p.mes, p.anio,
--        (SELECT COUNT(*) FROM responsable_gastos r
--          WHERE btrim(r.gasto) = btrim(a.ahorro) AND r.responsable = p.persona) AS n_resp
-- FROM pagos_ahorros p JOIN ahorros a ON a.id = p.ahorro_id
-- WHERE p.pagado AND p.monto IS NULL
-- ORDER BY a.ahorro, p.anio, p.mes, p.persona;
--
-- Montos rellenados por fondo y persona (Ahorro Común: Marco 553.46 / Chiara 928.20):
-- SELECT a.ahorro, p.persona, COUNT(*), MIN(p.monto), MAX(p.monto), SUM(p.monto)
-- FROM pagos_ahorros p JOIN ahorros a ON a.id = p.ahorro_id
-- WHERE p.pagado GROUP BY 1, 2 ORDER BY 1, 2;
--
-- Fondos recién migrados (saldo_inicial 0, fecha_corte NULL) y sin retiros aún:
-- SELECT id, ahorro, total, saldo_inicial, fecha_corte FROM ahorros ORDER BY ahorro;
-- SELECT COUNT(*) FILTER (WHERE fondo_id IS NOT NULL) AS retiros,
--        COUNT(*) FILTER (WHERE pagado_por IS NOT NULL) AS con_pagado_por
-- FROM gastos_variables;
--
-- ============================================================
-- REVERSIÓN (ejecutar a mano)
-- ============================================================
-- Revertir primero el CÓDIGO (el código nuevo lee estas columnas y
-- fallaría sin ellas). Si ya se cargaron datos desde la UI (saldos de
-- partida, retiros marcados con fondo, quién pagó, montos de depósitos
-- nuevos), respaldarlos antes de borrar las columnas: los DROP COLUMN
-- no se pueden deshacer después del COMMIT.
--
-- BEGIN;
-- SET LOCAL lock_timeout = '5s';
-- -- Respaldo (tablas normales; borrarlas cuando ya no hagan falta):
-- CREATE TABLE respaldo_002_pagos_ahorros AS
--     SELECT id, monto FROM pagos_ahorros WHERE monto IS NOT NULL;
-- CREATE TABLE respaldo_002_ahorros AS
--     SELECT id, ahorro, saldo_inicial, fecha_corte FROM ahorros
--     WHERE fecha_corte IS NOT NULL OR saldo_inicial <> 0;
-- CREATE TABLE respaldo_002_gastos_variables AS
--     SELECT id, fondo_id, pagado_por FROM gastos_variables
--     WHERE fondo_id IS NOT NULL OR pagado_por IS NOT NULL;
-- -- Borrar índice, restricciones y columnas (DROP COLUMN arrastra sus
-- -- CHECK/FK; se nombran igual para que quede explícito):
-- DROP INDEX IF EXISTS idx_gastos_variables_fondo_id;
-- ALTER TABLE gastos_variables DROP CONSTRAINT IF EXISTS gastos_variables_fondo_id_fkey;
-- ALTER TABLE gastos_variables DROP CONSTRAINT IF EXISTS gastos_variables_pagado_por_check;
-- ALTER TABLE gastos_variables DROP COLUMN IF EXISTS fondo_id;
-- ALTER TABLE gastos_variables DROP COLUMN IF EXISTS pagado_por;
-- ALTER TABLE ahorros DROP CONSTRAINT IF EXISTS ahorros_saldo_inicial_check;
-- ALTER TABLE ahorros DROP COLUMN IF EXISTS saldo_inicial;
-- ALTER TABLE ahorros DROP COLUMN IF EXISTS fecha_corte;
-- ALTER TABLE pagos_ahorros DROP CONSTRAINT IF EXISTS pagos_ahorros_monto_check;
-- ALTER TABLE pagos_ahorros DROP COLUMN IF EXISTS monto;
-- COMMIT;
--
-- Para volver a aplicar después con los datos respaldados: ejecutar
-- esta migración otra vez y luego
-- UPDATE pagos_ahorros p SET monto = r.monto FROM respaldo_002_pagos_ahorros r WHERE r.id = p.id;
-- UPDATE ahorros a SET saldo_inicial = r.saldo_inicial, fecha_corte = r.fecha_corte
--     FROM respaldo_002_ahorros r WHERE r.id = a.id;
-- UPDATE gastos_variables g SET fondo_id = r.fondo_id, pagado_por = r.pagado_por
--     FROM respaldo_002_gastos_variables r WHERE r.id = g.id;
-- (el relleno del paso 1 ya habrá puesto montos en filas viejas
-- marcadas: el primer UPDATE los pisa con los respaldados, que mandan).
-- Nota: el DROP COLUMN pierde además el vínculo retiro↔fondo, así que
-- tras revertir esos gastos vuelven a contar como gastos normales.
-- ============================================================
