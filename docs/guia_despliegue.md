# Guía de despliegue en AWS (paso a paso, desde la consola)

Todo en la región **us-east-2 (Ohio)**, la misma del bucket `e2-facturas-sebety`. Lambda, Glue y Athena deben crearse en esa región o no se podrán conectar al bucket.

> **Antes de empezar:** en Billing → Budgets creen un presupuesto de 5 USD con alerta por correo. Con los datos simulados el costo debería ser de centavos, pero así se enteran si algo se queda prendido.
>
> **Si usan AWS Academy (Learner Lab):** normalmente no se pueden crear roles en IAM; usen el rol existente (`LabRole`) cada vez que la consola pida uno para Lambda o Glue.

## 1. Bucket y zonas del lago
1. S3 → Create bucket → `e2-facturas-sebety`. Dejar "Block all public access" activado y el cifrado por defecto (SSE-S3).
2. Crear las carpetas: `raw/documentos/`, `raw/extraidos/`, `curated/comprobantes/`, `athena-results/`, `rechazados/`.
3. Management → Lifecycle rules: crear las reglas de `infra/lifecycle.json`. Desde la terminal también se puede:
   `aws s3api put-bucket-lifecycle-configuration --bucket e2-facturas-sebety --lifecycle-configuration file://infra/lifecycle.json`
4. 📸 Evidencia: lista de carpetas y reglas de ciclo de vida.

## 2. Lambda de ingesta (contenedor)
1. Construir la imagen: `docker build -t lector-tickets -f lambda/Dockerfile .`
2. ECR → Create repository `lector-tickets` → "View push commands" y seguir los 4 comandos que muestra.
3. Lambda → Create function → **Container image** → elegir la imagen. Memoria: 1024 MB · Timeout: 60 s.
4. Configuración → Asynchronous invocation: reintentos = 2 y una cola SQS como destino de fallos (DLQ).
5. Add trigger → S3 → bucket `e2-facturas-sebety`, evento "All object create events", prefijo `raw/documentos/`.
   ⚠️ El prefijo es obligatorio: si no, la Lambda se dispararía con sus propios JSON y entraría en un ciclo.
6. Prueba: subir unos archivos de `datos_simulados/raw/documentos/` respetando las carpetas, por ejemplo
   `aws s3 cp datos_simulados/raw/documentos s3://e2-facturas-sebety/raw/documentos --recursive`
7. 📸 Evidencia: JSON creados en `raw/extraidos/` y los logs en CloudWatch.

**Plan B si no pueden usar contenedores:** generar los JSON en local con `procesar_local.py` y subirlos directo a `raw/extraidos/`. El resto del lago funciona igual.

## 3. Job de Glue
1. Glue → ETL jobs → Script editor → Spark → pegar `glue/raw_a_curated.py`.
2. Job details: rol con acceso al bucket · Glue 4.0 · Worker G.1X · **2 workers** (el mínimo, es lo más barato) · Timeout 10 min.
3. Job parameters:
   - `--RAW_PATH` = `s3://e2-facturas-sebety/raw/extraidos/`
   - `--CURATED_PATH` = `s3://e2-facturas-sebety/curated/comprobantes/`
4. Run → esperar "Succeeded". 📸 Evidencia: corrida exitosa y carpetas `anio=/mes=` en curated.
5. (Opcional) Schedule: diario a las 2 a.m. o el día 1 de cada mes.

## 4. Athena
1. Settings → Query result location = `s3://e2-facturas-sebety/athena-results/`.
2. Correr `athena/01_crear_tablas.sql` (una sentencia a la vez; ya trae el nombre del bucket).
3. Correr las 3 consultas de `athena/02_consultas.sql` y anotar los **Data scanned** en `evidencias/athena_bytes.md`.

## 5. Al terminar
- Lambda, Glue y Athena no cobran si no se usan. Revisen que no quede ninguna instancia EC2 prendida de la entrega anterior.
