-- ============================================================
-- GASTOS VARIABLES: Tab 1 entries
-- ============================================================
CREATE TABLE IF NOT EXISTS gastos_variables (
    id          SERIAL PRIMARY KEY,
    persona     VARCHAR(50)     NOT NULL CHECK (persona IN ('Marco', 'Chiara')),
    descripcion TEXT            NOT NULL,
    categoria   VARCHAR(50)     NOT NULL,
    monto       NUMERIC(12, 2)  NOT NULL CHECK (monto > 0),
    fecha       DATE            NOT NULL,
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

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
