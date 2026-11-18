# Imagen de contenedor para la Lambda de ingesta.
# Tesseract no viene incluido en Lambda, por eso se empaqueta en una imagen propia
# (hasta 10 GB) en lugar de un .zip (límite de 250 MB descomprimido).
#
# Construir desde la raíz del repositorio:
#   docker build -t lector-tickets -f lambda/Dockerfile .
# Probar en local (en otra terminal mandar un evento con curl):
#   docker run -p 9000:8080 --entrypoint /usr/local/bin/aws-lambda-rie lector-tickets \
#     python -m awslambdaric lambda_function.handler
#   curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d @lambda/evento_prueba.json
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa curl \
 && curl -Lo /usr/local/bin/aws-lambda-rie https://github.com/aws/aws-lambda-runtime-interface-emulator/releases/latest/download/aws-lambda-rie \
 && chmod +x /usr/local/bin/aws-lambda-rie \
 && apt-get purge -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /var/task
COPY lambda/requirements-lambda.txt .
RUN pip install --no-cache-dir -r requirements-lambda.txt awslambdaric boto3

COPY src/lector ./lector
COPY src/lambda_function.py .

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["lambda_function.handler"]
