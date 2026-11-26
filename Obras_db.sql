-- =============================================================================
-- SISTEMA ADMINISTRADOR DE OBRAS PÚBLICAS (PostgreSQL - 32 Tablas en 3NF Estricta)
-- 100% sincronizado con app/models_base.py
-- =============================================================================

-- =============================================================================
-- BLOQUE 1: CATÁLOGOS MAESTROS INSTITUCIONALES (14 Tablas)
-- =============================================================================

-- 1. Catálogo de Roles Únicos del Sistema
CREATE TABLE IF NOT EXISTS Rol_Usuario (
    id_rol_usuario SERIAL PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE,
    descripcion VARCHAR(255),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_rol_usuario_nombre ON Rol_Usuario (nombre);

-- 2. Catálogo Maestro de Estatus por Ámbito
CREATE TABLE IF NOT EXISTS Cat_Estatus (
    id_estatus SERIAL PRIMARY KEY,
    ambito VARCHAR(30) NOT NULL,
    clave VARCHAR(50) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_estatus_ambito_clave UNIQUE (ambito, clave)
);
CREATE INDEX IF NOT EXISTS ix_cat_estatus_ambito ON Cat_Estatus (ambito);
CREATE INDEX IF NOT EXISTS ix_cat_estatus_clave ON Cat_Estatus (clave);

-- 3. Catálogo de Unidades de Medida
CREATE TABLE IF NOT EXISTS Cat_Unidades_Medida (
    id_unidad SERIAL PRIMARY KEY,
    clave VARCHAR(20) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_unidades_medida_clave ON Cat_Unidades_Medida (clave);

-- 4. Catálogo de Partidas Presupuestales (3NF)
CREATE TABLE IF NOT EXISTS Cat_Partidas (
    id_partida SERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL UNIQUE,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_partidas_nombre ON Cat_Partidas (nombre);

-- 5. Catálogo de Subpartidas Presupuestales (3NF)
CREATE TABLE IF NOT EXISTS Cat_Subpartidas (
    id_subpartida SERIAL PRIMARY KEY,
    id_partida INTEGER NOT NULL REFERENCES Cat_Partidas (id_partida),
    nombre VARCHAR(120) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_subpartida_por_partida UNIQUE (id_partida, nombre)
);
CREATE INDEX IF NOT EXISTS ix_cat_subpartidas_id_partida ON Cat_Subpartidas (id_partida);
CREATE INDEX IF NOT EXISTS ix_cat_subpartidas_nombre ON Cat_Subpartidas (nombre);

-- 6. Catálogo de Tipos de Concepto de Obra
CREATE TABLE IF NOT EXISTS Cat_Tipo_Concepto (
    id_tipo_concepto SERIAL PRIMARY KEY,
    clave VARCHAR(30) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    requiere_apu BOOLEAN NOT NULL DEFAULT FALSE,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_tipo_concepto_clave ON Cat_Tipo_Concepto (clave);

-- 7. Catálogo Maestro General de Conceptos de Obra (Libro / Tabulador 3NF)
CREATE TABLE IF NOT EXISTS Cat_Conceptos_Maestro (
    id_concepto_maestro SERIAL PRIMARY KEY,
    id_subpartida INTEGER NOT NULL REFERENCES Cat_Subpartidas (id_subpartida),
    id_unidad INTEGER NOT NULL REFERENCES Cat_Unidades_Medida (id_unidad),
    clave_concepto VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT NOT NULL,
    precio_referencia NUMERIC(15, 2),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_precio_ref_positivo CHECK (precio_referencia IS NULL OR precio_referencia > 0)
);
CREATE INDEX IF NOT EXISTS ix_cat_conceptos_maestro_id_subpartida ON Cat_Conceptos_Maestro (id_subpartida);
CREATE INDEX IF NOT EXISTS ix_cat_conceptos_maestro_clave_concepto ON Cat_Conceptos_Maestro (clave_concepto);

-- 8. Catálogo de Tipos de Estimación
CREATE TABLE IF NOT EXISTS Cat_Tipo_Estimacion (
    id_tipo_estimacion SERIAL PRIMARY KEY,
    clave VARCHAR(40) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    descripcion TEXT,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_tipo_estimacion_clave ON Cat_Tipo_Estimacion (clave);

-- 9. Catálogo de Tipos de Póliza de Fianza
CREATE TABLE IF NOT EXISTS Cat_Tipo_Poliza (
    id_tipo_poliza SERIAL PRIMARY KEY,
    clave VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_tipo_poliza_clave ON Cat_Tipo_Poliza (clave);

-- 10. Catálogo de Tipos de Nota de Bitácora
CREATE TABLE IF NOT EXISTS Cat_Tipo_Nota_Bitacora (
    id_tipo_nota SERIAL PRIMARY KEY,
    clave VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    id_rol_exclusivo INTEGER REFERENCES Rol_Usuario (id_rol_usuario),
    min_imagenes INTEGER NOT NULL DEFAULT 0,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_tipo_nota_bitacora_clave ON Cat_Tipo_Nota_Bitacora (clave);

-- 11. Catálogo de Tipos de Ensayo de Laboratorio
CREATE TABLE IF NOT EXISTS Cat_Tipo_Ensayo (
    id_tipo_ensayo SERIAL PRIMARY KEY,
    clave VARCHAR(40) NOT NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    norma_referencia VARCHAR(100),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_cat_tipo_ensayo_clave ON Cat_Tipo_Ensayo (clave);

-- 12. Catálogo de Tipos de Acción de Auditoría
CREATE TABLE IF NOT EXISTS Tipo_Accion (
    id_accion SERIAL PRIMARY KEY,
    tipo_accion VARCHAR(100) NOT NULL,
    accion_ejecutada VARCHAR(255) NOT NULL UNIQUE,
    descripcion TEXT,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_tipo_accion_accion_ejecutada ON Tipo_Accion (accion_ejecutada);

-- 13. Padrón de Empresas Contratistas
CREATE TABLE IF NOT EXISTS Contratistas (
    id_contratista SERIAL PRIMARY KEY,
    rfc VARCHAR(13) NOT NULL UNIQUE,
    razon_social VARCHAR(255) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_contratistas_rfc ON Contratistas (rfc);

-- 14. Diccionario de Correos y Dominios Autorizados
CREATE TABLE IF NOT EXISTS Cat_Correos_Autorizados (
    id_correo_autorizado SERIAL PRIMARY KEY,
    id_contratista INTEGER REFERENCES Contratistas (id_contratista),
    tipo_registro VARCHAR(20) NOT NULL,
    valor VARCHAR(150) NOT NULL UNIQUE,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_tipo_registro_correo CHECK (tipo_registro IN ('DOMINIO', 'CORREO'))
);
CREATE INDEX IF NOT EXISTS ix_cat_correos_autorizados_id_contratista ON Cat_Correos_Autorizados (id_contratista);
CREATE INDEX IF NOT EXISTS ix_cat_correos_autorizados_valor ON Cat_Correos_Autorizados (valor);

-- =============================================================================
-- BLOQUE 2: TABLAS OPERATIVAS NORMALIZADAS EN 3NF ESTRICTA (18 Tablas)
-- =============================================================================

-- 15. Usuarios
CREATE TABLE IF NOT EXISTS Usuarios (
    id_usuario SERIAL PRIMARY KEY,
    id_rol_usuario INTEGER NOT NULL REFERENCES Rol_Usuario (id_rol_usuario),
    nombre_completo VARCHAR(255) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    firma_electronica VARCHAR(255),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS ix_usuarios_correo ON Usuarios (correo);

-- 16. Obras Públicas
CREATE TABLE IF NOT EXISTS Obras (
    id_obra SERIAL PRIMARY KEY,
    id_estatus INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    nombre_obra VARCHAR(255) NOT NULL,
    presupuesto_total NUMERIC(15, 2) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    CONSTRAINT chk_presupuesto_obra_positivo CHECK (presupuesto_total > 0),
    CONSTRAINT chk_fechas_obra CHECK (fecha_fin >= fecha_inicio)
);

-- 17. Asignaciones de Personal Operativo
CREATE TABLE IF NOT EXISTS Obras_Asignaciones (
    id_asignacion SERIAL PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES Usuarios (id_usuario),
    id_obra INTEGER NOT NULL REFERENCES Obras (id_obra),
    fecha_inicio_asignacion DATE NOT NULL,
    fecha_fin_asignacion DATE,
    CONSTRAINT chk_fechas_asignacion CHECK (fecha_fin_asignacion IS NULL OR fecha_fin_asignacion >= fecha_inicio_asignacion)
);
CREATE INDEX IF NOT EXISTS ix_obras_asignaciones_id_usuario ON Obras_Asignaciones (id_usuario);
CREATE INDEX IF NOT EXISTS ix_obras_asignaciones_id_obra ON Obras_Asignaciones (id_obra);

-- 18. Contratos Legales
CREATE TABLE IF NOT EXISTS Contratos (
    id_contrato SERIAL PRIMARY KEY,
    id_obra INTEGER NOT NULL UNIQUE REFERENCES Obras (id_obra),
    id_contratista INTEGER NOT NULL REFERENCES Contratistas (id_contratista),
    id_estatus INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    numero_contrato VARCHAR(100) NOT NULL UNIQUE,
    monto_contrato NUMERIC(15, 2) NOT NULL,
    monto_anticipo NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    archivo_contrato VARCHAR(255),
    CONSTRAINT chk_monto_contrato_positivo CHECK (monto_contrato > 0),
    CONSTRAINT chk_monto_anticipo_rango CHECK (monto_anticipo >= 0 AND monto_anticipo <= monto_contrato)
);
CREATE INDEX IF NOT EXISTS ix_contratos_id_obra ON Contratos (id_obra);
CREATE INDEX IF NOT EXISTS ix_contratos_numero_contrato ON Contratos (numero_contrato);

-- 19. Pólizas de Fianza
CREATE TABLE IF NOT EXISTS Polizas (
    id_poliza SERIAL PRIMARY KEY,
    id_contrato INTEGER NOT NULL REFERENCES Contratos (id_contrato),
    id_tipo_poliza INTEGER NOT NULL REFERENCES Cat_Tipo_Poliza (id_tipo_poliza),
    numero_poliza VARCHAR(100) NOT NULL UNIQUE,
    fecha_vencimiento DATE NOT NULL,
    archivo_poliza VARCHAR(255) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_polizas_id_contrato ON Polizas (id_contrato);
CREATE INDEX IF NOT EXISTS ix_polizas_numero_poliza ON Polizas (numero_poliza);

-- 20. Conceptos Asignados por Obra (3NF: Tabla asociativa Obras <-> Cat_Conceptos_Maestro)
CREATE TABLE IF NOT EXISTS Obra_Conceptos (
    id_obra_concepto SERIAL PRIMARY KEY,
    id_obra INTEGER NOT NULL REFERENCES Obras (id_obra),
    id_concepto_maestro INTEGER NOT NULL REFERENCES Cat_Conceptos_Maestro (id_concepto_maestro),
    id_tipo_concepto INTEGER NOT NULL REFERENCES Cat_Tipo_Concepto (id_tipo_concepto),
    cantidad_presupuestada NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    cantidad_adicional_autorizada NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    precio_unitario NUMERIC(15, 2) NOT NULL,
    dictamen_apu_url VARCHAR(255),
    autorizado_por_residente BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_concepto_maestro_por_obra UNIQUE (id_obra, id_concepto_maestro),
    CONSTRAINT chk_cant_presupuestada CHECK (cantidad_presupuestada >= 0),
    CONSTRAINT chk_cant_adicional CHECK (cantidad_adicional_autorizada >= 0),
    CONSTRAINT chk_precio_unitario_positivo CHECK (precio_unitario > 0)
);
CREATE INDEX IF NOT EXISTS ix_obra_conceptos_id_obra ON Obra_Conceptos (id_obra);
CREATE INDEX IF NOT EXISTS ix_obra_conceptos_id_concepto_maestro ON Obra_Conceptos (id_concepto_maestro);

-- 21. Estimaciones de Obra
CREATE TABLE IF NOT EXISTS Estimaciones (
    id_estimacion SERIAL PRIMARY KEY,
    id_obra INTEGER NOT NULL REFERENCES Obras (id_obra),
    id_superintendente INTEGER NOT NULL REFERENCES Usuarios (id_usuario),
    id_tipo_estimacion INTEGER NOT NULL REFERENCES Cat_Tipo_Estimacion (id_tipo_estimacion),
    id_estatus INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    numero_estimacion INTEGER NOT NULL,
    version_subsanacion INTEGER NOT NULL DEFAULT 1,
    periodo_inicio DATE NOT NULL,
    periodo_fin DATE NOT NULL,
    fecha_presentacion DATE NOT NULL DEFAULT CURRENT_DATE,
    monto_bruto NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    monto_amortizacion NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    iva NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    retencion_atraso NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    retencion_sfp NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    monto_neto NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    CONSTRAINT uq_numero_estimacion_obra UNIQUE (id_obra, numero_estimacion),
    CONSTRAINT chk_numero_estimacion_positivo CHECK (numero_estimacion > 0),
    CONSTRAINT chk_version_subsanacion_min CHECK (version_subsanacion >= 1),
    CONSTRAINT chk_periodo_estimacion CHECK (periodo_fin >= periodo_inicio),
    CONSTRAINT chk_iva_no_negativo CHECK (iva >= 0),
    CONSTRAINT chk_retencion_atraso_no_negativa CHECK (retencion_atraso >= 0),
    CONSTRAINT chk_retencion_sfp_no_negativa CHECK (retencion_sfp >= 0)
);
CREATE INDEX IF NOT EXISTS ix_estimaciones_id_obra ON Estimaciones (id_obra);

-- 22. Detalles por Concepto de Estimaciones (3NF)
CREATE TABLE IF NOT EXISTS Estimacion_Detalles (
    id_estimacion_detalle SERIAL PRIMARY KEY,
    id_estimacion INTEGER NOT NULL REFERENCES Estimaciones (id_estimacion),
    id_obra_concepto INTEGER NOT NULL REFERENCES Obra_Conceptos (id_obra_concepto),
    cantidad_estimada NUMERIC(15, 2) NOT NULL,
    CONSTRAINT uq_detalle_estimacion_concepto UNIQUE (id_estimacion, id_obra_concepto),
    CONSTRAINT chk_cant_estimada_pos CHECK (cantidad_estimada > 0)
);
CREATE INDEX IF NOT EXISTS ix_estimacion_detalles_id_estimacion ON Estimacion_Detalles (id_estimacion);
CREATE INDEX IF NOT EXISTS ix_estimacion_detalles_id_obra_concepto ON Estimacion_Detalles (id_obra_concepto);

-- 23. Revisión y Dictamen de Estimaciones
CREATE TABLE IF NOT EXISTS Revision_Estimaciones (
    id_revision SERIAL PRIMARY KEY,
    id_estimacion INTEGER NOT NULL REFERENCES Estimaciones (id_estimacion),
    id_supervisor INTEGER NOT NULL REFERENCES Usuarios (id_usuario),
    id_estatus_revision INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    version_revisada INTEGER NOT NULL DEFAULT 1,
    fecha_recepcion DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_autorizacion DATE,
    observaciones_rechazo TEXT,
    monto_autorizado_neto NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    sello_firma_supervisor VARCHAR(255),
    CONSTRAINT uq_revision_estimacion_version UNIQUE (id_estimacion, version_revisada),
    CONSTRAINT chk_version_revisada_rev CHECK (version_revisada >= 1)
);
CREATE INDEX IF NOT EXISTS ix_revision_estimaciones_id_estimacion ON Revision_Estimaciones (id_estimacion);

-- 24. Documentos Fiscales CFDI
CREATE TABLE IF NOT EXISTS Facturacion_Estimacion (
    id_factura SERIAL PRIMARY KEY,
    id_estimacion INTEGER NOT NULL UNIQUE REFERENCES Estimaciones (id_estimacion),
    folio_fiscal VARCHAR(100) NOT NULL UNIQUE,
    monto_factura NUMERIC(15, 2) NOT NULL,
    ruta_pdf VARCHAR(255) NOT NULL,
    ruta_xml VARCHAR(255) NOT NULL,
    fecha_carga TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_monto_factura_positivo CHECK (monto_factura > 0)
);
CREATE INDEX IF NOT EXISTS ix_facturacion_estimacion_id_estimacion ON Facturacion_Estimacion (id_estimacion);
CREATE INDEX IF NOT EXISTS ix_facturacion_estimacion_folio_fiscal ON Facturacion_Estimacion (folio_fiscal);

-- 25. Estimaciones Pagadas
CREATE TABLE IF NOT EXISTS Estimaciones_Pagadas (
    id_estimacion INTEGER PRIMARY KEY REFERENCES Estimaciones (id_estimacion),
    id_estatus_pago INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    folio_estimacion VARCHAR(100) NOT NULL UNIQUE,
    monto_pagado NUMERIC(15, 2) NOT NULL,
    fecha_pago DATE NOT NULL,
    CONSTRAINT chk_monto_pagado_positivo CHECK (monto_pagado > 0)
);
CREATE INDEX IF NOT EXISTS ix_estimaciones_pagadas_folio_estimacion ON Estimaciones_Pagadas (folio_estimacion);

-- 26. Reporte Diario de Supervisión (3NF: id_estatus_reporte FK -> Cat_Estatus, incidentes en tabla hija)
CREATE TABLE IF NOT EXISTS Reporte_Diario_Supervision (
    id_reporte SERIAL PRIMARY KEY,
    id_obra INTEGER NOT NULL REFERENCES Obras (id_obra),
    id_supervisor INTEGER NOT NULL REFERENCES Usuarios (id_usuario),
    id_estatus_reporte INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    fecha_reporte DATE NOT NULL,
    actividades_realizadas TEXT,
    clima VARCHAR(20),
    horas_lluvia NUMERIC(4, 2) NOT NULL DEFAULT 0.00,
    maquinaria_cantidad INTEGER NOT NULL DEFAULT 0,
    equipo_cantidad INTEGER NOT NULL DEFAULT 0,
    personal_cantidad INTEGER NOT NULL DEFAULT 0,
    porcentaje_avance_reportado NUMERIC(5, 2),
    sello_digital VARCHAR(255),
    fecha_envio TIMESTAMP,
    fecha_firma TIMESTAMP,
    CONSTRAINT uq_reporte_diario_obra_fecha UNIQUE (id_obra, fecha_reporte),
    CONSTRAINT chk_clima_reporte CHECK (clima IS NULL OR clima IN ('SOLEADO', 'NUBLADO', 'LLUVIOSO', 'TORMENTA')),
    CONSTRAINT chk_horas_lluvia CHECK (horas_lluvia >= 0 AND horas_lluvia <= 24),
    CONSTRAINT chk_maquinaria_no_negativa CHECK (maquinaria_cantidad >= 0),
    CONSTRAINT chk_equipo_no_negativo CHECK (equipo_cantidad >= 0),
    CONSTRAINT chk_personal_no_negativo CHECK (personal_cantidad >= 0),
    CONSTRAINT chk_porcentaje_avance_rango CHECK (porcentaje_avance_reportado IS NULL OR (porcentaje_avance_reportado >= 0 AND porcentaje_avance_reportado <= 100))
);
CREATE INDEX IF NOT EXISTS ix_reporte_diario_supervision_id_obra ON Reporte_Diario_Supervision (id_obra);
CREATE INDEX IF NOT EXISTS ix_reporte_diario_supervision_id_estatus_reporte ON Reporte_Diario_Supervision (id_estatus_reporte);

-- 27. Incidentes de Reporte Diario de Supervisión (3NF)
CREATE TABLE IF NOT EXISTS Reporte_Incidentes (
    id_incidente SERIAL PRIMARY KEY,
    id_reporte INTEGER NOT NULL REFERENCES Reporte_Diario_Supervision (id_reporte),
    id_estatus_incidente INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    suceso TEXT NOT NULL,
    accion_solucion TEXT
);
CREATE INDEX IF NOT EXISTS ix_reporte_incidentes_id_reporte ON Reporte_Incidentes (id_reporte);
CREATE INDEX IF NOT EXISTS ix_reporte_incidentes_id_estatus_incidente ON Reporte_Incidentes (id_estatus_incidente);

-- 28. Cortes Oficiales de Avance Físico y Financiero Real
CREATE TABLE IF NOT EXISTS Avances_Fisicos (
    id_avance SERIAL PRIMARY KEY,
    id_obra INTEGER NOT NULL REFERENCES Obras (id_obra),
    id_reporte INTEGER REFERENCES Reporte_Diario_Supervision (id_reporte),
    fecha_corte DATE NOT NULL,
    porcentaje_fisico NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    porcentaje_financiero_real NUMERIC(5, 2) NOT NULL DEFAULT 0.00,
    CONSTRAINT chk_candado_fisico_financiero CHECK (porcentaje_financiero_real <= porcentaje_fisico),
    CONSTRAINT chk_fisico_rango CHECK (porcentaje_fisico >= 0 AND porcentaje_fisico <= 100),
    CONSTRAINT chk_fin_rango CHECK (porcentaje_financiero_real >= 0 AND porcentaje_financiero_real <= 100)
);
CREATE INDEX IF NOT EXISTS ix_avances_fisicos_id_obra ON Avances_Fisicos (id_obra);
CREATE INDEX IF NOT EXISTS ix_avances_fisicos_id_reporte ON Avances_Fisicos (id_reporte);

-- 29. Bitácora Electrónica de Obra Inmutable
CREATE TABLE IF NOT EXISTS Bitacora_Notas (
    id_nota SERIAL PRIMARY KEY,
    id_obra INTEGER NOT NULL REFERENCES Obras (id_obra),
    id_usuario INTEGER NOT NULL REFERENCES Usuarios (id_usuario),
    id_tipo_nota INTEGER NOT NULL REFERENCES Cat_Tipo_Nota_Bitacora (id_tipo_nota),
    consecutivo_nota INTEGER NOT NULL,
    asunto VARCHAR(255) NOT NULL,
    descripcion TEXT NOT NULL,
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    firmada BOOLEAN NOT NULL DEFAULT FALSE,
    sello_digital VARCHAR(255),
    CONSTRAINT uq_consecutivo_bitacora_obra UNIQUE (id_obra, consecutivo_nota),
    CONSTRAINT chk_consecutivo_nota_min CHECK (consecutivo_nota >= 1)
);
CREATE INDEX IF NOT EXISTS ix_bitacora_notas_id_obra ON Bitacora_Notas (id_obra);

-- 30. Evidencia Fotográfica Adjunta
CREATE TABLE IF NOT EXISTS Evidencia_Adjunta (
    id_evidencia SERIAL PRIMARY KEY,
    id_nota INTEGER REFERENCES Bitacora_Notas (id_nota),
    id_reporte INTEGER REFERENCES Reporte_Diario_Supervision (id_reporte),
    ruta_archivo VARCHAR(255) NOT NULL,
    descripcion_pie_foto VARCHAR(255),
    fecha_carga TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_evidencia_origen_unico CHECK ((id_nota IS NOT NULL AND id_reporte IS NULL) OR (id_nota IS NULL AND id_reporte IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_evidencia_adjunta_id_nota ON Evidencia_Adjunta (id_nota);
CREATE INDEX IF NOT EXISTS ix_evidencia_adjunta_id_reporte ON Evidencia_Adjunta (id_reporte);

-- 31. Control de Calidad y Pruebas de Laboratorio
CREATE TABLE IF NOT EXISTS Control_Calidad_Pruebas (
    id_prueba SERIAL PRIMARY KEY,
    id_obra_concepto INTEGER NOT NULL REFERENCES Obra_Conceptos (id_obra_concepto),
    id_tipo_ensayo INTEGER NOT NULL REFERENCES Cat_Tipo_Ensayo (id_tipo_ensayo),
    id_estatus_dictamen INTEGER NOT NULL REFERENCES Cat_Estatus (id_estatus),
    fecha_muestreo DATE NOT NULL,
    valor_obtenido VARCHAR(100) NOT NULL,
    url_reporte_laboratorio VARCHAR(255) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_control_calidad_pruebas_id_obra_concepto ON Control_Calidad_Pruebas (id_obra_concepto);

-- 32. Registro Inmutable de Auditoría
CREATE TABLE IF NOT EXISTS Auditoria_Logs (
    id_log SERIAL PRIMARY KEY,
    id_obra INTEGER REFERENCES Obras (id_obra),
    id_usuario INTEGER NOT NULL REFERENCES Usuarios (id_usuario),
    id_accion INTEGER NOT NULL REFERENCES Tipo_Accion (id_accion),
    ip_origen VARCHAR(45),
    fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
