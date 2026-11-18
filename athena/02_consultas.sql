-- =====================================================================
-- Las 3 consultas de la entrega. Después de correr cada una, anotar en
-- evidencias/athena_bytes.md los "Data scanned" que muestra Athena
-- (abajo del resultado, o en la pestaña "Recent queries").
-- =====================================================================

-- ---------------------------------------------------------------------
-- Consulta 1. Gasto mensual por usuario (control de gastos del usuario)
-- Lee todas las particiones, pero solo 4 columnas del Parquet.
-- ---------------------------------------------------------------------
SELECT anio,
       mes,
       id_usuario_hash,
       COUNT(*)               AS comprobantes,
       SUM(subtotal)          AS subtotal,
       SUM(iva)               AS iva_acreditable,
       SUM(total)             AS gasto_total
FROM facturas_db.comprobantes
WHERE NOT es_duplicado
GROUP BY anio, mes, id_usuario_hash
ORDER BY anio, mes, gasto_total DESC;

-- ---------------------------------------------------------------------
-- Consulta 2. Gasto por categoría en un mes (cierre mensual)
-- El filtro por anio/mes hace que Athena lea SOLO esa carpeta: así se
-- demuestra el ahorro del particionado.
-- ---------------------------------------------------------------------
SELECT categoria,
       COUNT(*)                                        AS comprobantes,
       SUM(total)                                      AS gasto_total,
       ROUND(100.0 * SUM(total) / SUM(SUM(total)) OVER (), 1) AS porcentaje
FROM facturas_db.comprobantes
WHERE anio = '2026' AND mes = '10'
  AND NOT es_duplicado
GROUP BY categoria
ORDER BY gasto_total DESC;

-- ---------------------------------------------------------------------
-- Consulta 3. Calidad: comprobantes duplicados
--   a) CFDI con el mismo folio fiscal (UUID) subido más de una vez
--   b) tickets sospechosos: mismo comercio, misma fecha y mismo total
-- ---------------------------------------------------------------------
SELECT 'cfdi_mismo_uuid'   AS tipo_duplicado, uuid_cfdi AS llave, COUNT(*) AS veces,
       ARRAY_JOIN(ARRAY_AGG(id_documento), ', ') AS documentos
FROM facturas_db.comprobantes
WHERE uuid_cfdi IS NOT NULL AND uuid_cfdi <> ''
GROUP BY uuid_cfdi
HAVING COUNT(*) > 1
UNION ALL
SELECT 'ticket_sospechoso', CONCAT(rfc_emisor, '|', CAST(fecha_emision AS varchar), '|', CAST(total AS varchar)),
       COUNT(*), ARRAY_JOIN(ARRAY_AGG(id_documento), ', ')
FROM facturas_db.comprobantes
WHERE uuid_cfdi IS NULL OR uuid_cfdi = ''
GROUP BY rfc_emisor, fecha_emision, total
HAVING COUNT(*) > 1;

-- ---------------------------------------------------------------------
-- Extra (para la evidencia de costos): la MISMA consulta 2 sobre la zona
-- raw en JSON. Comparar los bytes leídos contra la consulta 2.
-- ---------------------------------------------------------------------
SELECT categoria, COUNT(*) AS comprobantes, SUM(total) AS gasto_total
FROM facturas_db.raw_extraidos
WHERE estatus = 'procesado'
  AND SUBSTR(fecha_emision, 1, 7) = '2026-10'
GROUP BY categoria
ORDER BY gasto_total DESC;

-- ---------------------------------------------------------------------
-- Extra (calidad): por qué se rechazan los documentos
-- ---------------------------------------------------------------------
SELECT motivo_rechazo, tipo_archivo, COUNT(*) AS documentos
FROM facturas_db.raw_extraidos
WHERE estatus = 'rechazado'
GROUP BY motivo_rechazo, tipo_archivo
ORDER BY documentos DESC;
