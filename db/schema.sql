-- ============================================================
-- GASTOS VARIABLES: Tab 1 entries
-- ============================================================
CREATE TABLE IF NOT EXISTS gastos_variables (
    id              SERIAL PRIMARY KEY,
    persona         VARCHAR(50)     NOT NULL CHECK (persona IN ('Marco', 'Chiara')),
    descripcion     TEXT            NOT NULL,
    categoria       VARCHAR(50)     NOT NULL,
    monto           NUMERIC(12, 2)  NOT NULL CHECK (monto > 0),
    fecha           DATE            NOT NULL,
    tipo_de_gasto   VARCHAR(50)     NOT NULL DEFAULT 'Gasto Común',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Migration: add tipo_de_gasto to existing deployments
ALTER TABLE gastos_variables ADD COLUMN IF NOT EXISTS tipo_de_gasto VARCHAR(50) NOT NULL DEFAULT 'Gasto Común';
DO $$ BEGIN
    ALTER TABLE gastos_variables ADD CONSTRAINT chk_tipo_de_gasto CHECK (tipo_de_gasto IN ('Gasto Común', 'Gasto Personal'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_gastos_variables_persona  ON gastos_variables (persona);
CREATE INDEX IF NOT EXISTS idx_gastos_variables_fecha    ON gastos_variables (fecha);
CREATE INDEX IF NOT EXISTS idx_gastos_variables_categoria ON gastos_variables (categoria);

-- ============================================================
-- GASTOS FIJOS: Tab 2, sub-tab 1
-- ============================================================
CREATE TABLE IF NOT EXISTS gastos_fijos (
    id      SERIAL PRIMARY KEY,
    gasto   VARCHAR(200)    NOT NULL UNIQUE,
    total   NUMERIC(12, 2)  NOT NULL CHECK (total >= 0)
);

-- ============================================================
-- INGRESOS: Tab 2, sub-tab 2
-- ============================================================
CREATE TABLE IF NOT EXISTS ingresos (
    id              SERIAL PRIMARY KEY,
    tipo_ingreso    VARCHAR(200)    NOT NULL,
    total           NUMERIC(12, 2)  NOT NULL CHECK (total >= 0),
    persona         VARCHAR(50)     NOT NULL CHECK (persona IN ('Marco', 'Chiara'))
);

-- ============================================================
-- AHORROS: Tab 2, sub-tab 3
-- ============================================================
CREATE TABLE IF NOT EXISTS ahorros (
    id      SERIAL PRIMARY KEY,
    ahorro  VARCHAR(200)    NOT NULL UNIQUE,
    total   NUMERIC(12, 2)  NOT NULL CHECK (total >= 0)
);

-- ============================================================
-- RESPONSABLE DE GASTOS: Tab 2, sub-tab 4
-- ============================================================
CREATE TABLE IF NOT EXISTS responsable_gastos (
    id          SERIAL PRIMARY KEY,
    gasto       VARCHAR(200)    NOT NULL,
    responsable VARCHAR(50)     NOT NULL CHECK (responsable IN ('Marco', 'Chiara', 'Ambos')),
    monto       NUMERIC(12, 2)  NOT NULL CHECK (monto >= 0)
);

-- ============================================================
-- PAGOS FIJOS: Tab 3 payment tracking
-- Each row records whether a persona paid a gasto_fijo
-- for a given month+year.
-- ============================================================
CREATE TABLE IF NOT EXISTS pagos_fijos (
    id              SERIAL PRIMARY KEY,
    gasto_fijo_id   INTEGER         NOT NULL REFERENCES gastos_fijos(id) ON DELETE CASCADE,
    persona         VARCHAR(50)     NOT NULL CHECK (persona IN ('Marco', 'Chiara')),
    mes             SMALLINT        NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio            SMALLINT        NOT NULL CHECK (anio >= 2020),
    pagado          BOOLEAN         NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (gasto_fijo_id, persona, mes, anio)
);

CREATE INDEX IF NOT EXISTS idx_pagos_fijos_periodo ON pagos_fijos (anio, mes);

-- ============================================================
-- PAGOS AHORROS: Tab visualizaciones — tracking depósitos de ahorro
-- Similar a pagos_fijos pero para la tabla ahorros.
-- ============================================================
CREATE TABLE IF NOT EXISTS pagos_ahorros (
    id          SERIAL PRIMARY KEY,
    ahorro_id   INTEGER         NOT NULL REFERENCES ahorros(id) ON DELETE CASCADE,
    persona     VARCHAR(50)     NOT NULL CHECK (persona IN ('Marco', 'Chiara')),
    mes         SMALLINT        NOT NULL CHECK (mes BETWEEN 1 AND 12),
    anio        SMALLINT        NOT NULL CHECK (anio >= 2020),
    pagado      BOOLEAN         NOT NULL DEFAULT FALSE,
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (ahorro_id, persona, mes, anio)
);

CREATE INDEX IF NOT EXISTS idx_pagos_ahorros_periodo ON pagos_ahorros (anio, mes);

-- ============================================================
-- VIAJES: etiqueta opcional de viaje para gastos_variables
-- Un gasto puede marcarse como ocurrido durante un viaje sin
-- cambiar su categoría. Independiente de `categoria`.
-- ============================================================
CREATE TABLE IF NOT EXISTS viajes (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(200)    NOT NULL,
    destino         VARCHAR(200),
    fecha_inicio    DATE            NOT NULL,
    fecha_fin       DATE            NOT NULL,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CHECK (fecha_fin >= fecha_inicio)
);

CREATE INDEX IF NOT EXISTS idx_viajes_fechas ON viajes (fecha_inicio, fecha_fin);

-- Migration: add nullable viaje_id to existing deployments
ALTER TABLE gastos_variables ADD COLUMN IF NOT EXISTS viaje_id INTEGER;
DO $$ BEGIN
    ALTER TABLE gastos_variables ADD CONSTRAINT gastos_variables_viaje_id_fkey FOREIGN KEY (viaje_id) REFERENCES viajes(id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_gastos_variables_viaje_id ON gastos_variables (viaje_id);
