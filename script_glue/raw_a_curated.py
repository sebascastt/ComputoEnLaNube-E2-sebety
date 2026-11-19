"""
Job de AWS Glue (Spark): raw/extraidos/ (JSON)  ->  curated/comprobantes/ (Parquet particionado)

Qué hace y por qué:
  - Solo pasa los comprobantes con estatus = 'procesado' (los rechazados se quedan en raw/)
  - Tipos claros: fechas como date, montos como decimal(12,2)
  - Seguridad: el RFC del receptor (dato personal del usuario) se reemplaza por un hash SHA-256
    y no se copia ningún nombre de persona. El analista puede contar por usuario sin saber quién es.
  - Duplicados: si el mismo CFDI (UUID) llegó dos veces, se marca es_duplicado = true
  - Costo: Parquet comprimido (snappy) y particionado por anio/mes, así Athena solo lee
    los meses que se consultan.

Parámetros del job (en Glue: "Job parameters"):
  --RAW_PATH      s3://<bucket>/raw/extraidos/
  --CURATED_PATH  s3://<bucket>/curated/comprobantes/
"""
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.window import Window

args = getResolvedOptions(sys.argv, ["JOB_NAME", "RAW_PATH", "CURATED_PATH"])
sc = SparkContext()
glue = GlueContext(sc)
spark = glue.spark_session
job = Job(glue)
job.init(args["JOB_NAME"], args)

# Sobrescribe solo las particiones (meses) que vienen en esta corrida, no toda la tabla
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

raw = spark.read.json(args["RAW_PATH"])
print(f"Registros en raw: {raw.count()}")

ok = raw.filter(F.col("estatus") == "procesado")

curated = (
    ok.select(
        F.col("id_documento"),
        F.sha2(F.col("id_usuario"), 256).alias("id_usuario_hash"),
        F.col("tipo_archivo"),
        F.col("metodo_lectura"),
        F.col("nombre_emisor"),
        F.col("rfc_emisor"),
        F.sha2(F.coalesce(F.col("rfc_receptor"), F.lit("")), 256).alias("rfc_receptor_hash"),
        F.to_date("fecha_emision").alias("fecha_emision"),
        F.col("subtotal").cast("decimal(12,2)").alias("subtotal"),
        F.col("iva").cast("decimal(12,2)").alias("iva"),
        F.col("total").cast("decimal(12,2)").alias("total"),
        F.coalesce(F.col("total_inferido"), F.lit(False)).alias("total_inferido"),
        F.upper(F.col("uuid_cfdi")).alias("uuid_cfdi"),
        F.col("categoria"),
        F.col("confianza").cast("double").alias("confianza_lectura"),
        F.to_timestamp("fecha_procesamiento").alias("fecha_procesamiento"),
        F.col("archivo_origen"),
    )
    .withColumn("anio", F.date_format("fecha_emision", "yyyy"))
    .withColumn("mes", F.date_format("fecha_emision", "MM"))
)

# El primer CFDI que llegó se queda como original; las copias con el mismo UUID se marcan
w = Window.partitionBy("uuid_cfdi").orderBy("fecha_procesamiento", "id_documento")
curated = curated.withColumn(
    "es_duplicado",
    F.when(F.col("uuid_cfdi").isNull() | (F.col("uuid_cfdi") == ""), F.lit(False))
     .otherwise(F.row_number().over(w) > 1),
)

(curated.repartition("anio", "mes")
        .write.mode("overwrite")
        .partitionBy("anio", "mes")
        .option("compression", "snappy")
        .parquet(args["CURATED_PATH"]))

print(f"Registros escritos en curated: {curated.count()}")
job.commit()
