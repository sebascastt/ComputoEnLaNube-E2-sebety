-- =====================================================================
-- Tablas en Athena (catálogo de Glue). Bucket: e2-facturas-sebety (región us-east-2, Ohio).
-- Antes de la primera consulta: en Athena > Settings, poner como ubicación
-- de resultados s3://e2-facturas-sebety/athena-results/
-- =====================================================================

CREATE DATABASE IF NOT EXISTS facturas_db;

-- ---------------------------------------------------------------------
-- Zona RAW: lo que escribe Lambda, en JSON (un archivo por documento)
-- ---------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS facturas_db.raw_extraidos (
  id_documento         string,
  id_usuario           string,
  archivo_origen       string,
  tipo_archivo         string,
  tamano_bytes         bigint,
  nombre_emisor        string,
  rfc_emisor           string,
  rfc_receptor         string,
  fecha_emision        string,
  subtotal             double,
  iva                  double,
  total                double,
  total_inferido       boolean,
  uuid_cfdi            string,
  metodo_lectura       string,
  confianza            double,
  nitidez              double,
  categoria            string,
  estatus              string,
  motivo_rechazo       string,
  fecha_procesamiento  string,
  version_lector       string
)
PARTITIONED BY (fecha_carga string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://e2-facturas-sebety/raw/extraidos/';

MSCK REPAIR TABLE facturas_db.raw_extraidos;   -- registra las carpetas fecha_carga=...

-- ---------------------------------------------------------------------
-- Zona CURATED: lo que escribe el job de Glue, en Parquet por anio/mes
-- Sin datos personales en claro: usuario y RFC receptor van como hash
-- ---------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS facturas_db.comprobantes (
  id_documento         string,
  id_usuario_hash      string,
  tipo_archivo         string,
  metodo_lectura       string,
  nombre_emisor        string,
  rfc_emisor           string,
  rfc_receptor_hash    string,
  fecha_emision        date,
  subtotal             decimal(12,2),
  iva                  decimal(12,2),
  total                decimal(12,2),
  total_inferido       boolean,
  uuid_cfdi            string,
  categoria            string,
  confianza_lectura    double,
  fecha_procesamiento  timestamp,
  archivo_origen       string,
  es_duplicado         boolean
)
PARTITIONED BY (anio string, mes string)
STORED AS PARQUET
LOCATION 's3://e2-facturas-sebety/curated/comprobantes/'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

MSCK REPAIR TABLE facturas_db.comprobantes;    -- registra anio=.../mes=...
