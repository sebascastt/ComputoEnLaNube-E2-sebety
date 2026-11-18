"""
Limpieza de imagen con OpenCV antes del OCR.

OpenCV NO lee texto: prepara la imagen para que Tesseract la lea mejor.
Pasos: escala de grises -> recorte del ticket -> enderezado -> quitar ruido -> binarizar.
"""
import cv2
import numpy as np


def a_grises(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def recortar_papel(gris: np.ndarray) -> np.ndarray:
    """Ubica el papel (zona clara más grande) y recorta el fondo de la mesa."""
    _, mascara = cv2.threshold(cv2.GaussianBlur(gris, (5, 5), 0), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contornos, _ = cv2.findContours(mascara, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contornos:
        return gris
    c = max(contornos, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.2 * gris.size:
        return gris
    x, y, w, h = cv2.boundingRect(c)
    return gris[y:y + h, x:x + w]


def angulo_inclinacion(gris: np.ndarray) -> float:
    """Estima cuántos grados está chueco el texto usando sus píxeles oscuros."""
    _, binaria = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binaria > 0))
    if len(coords) < 100:
        return 0.0
    angulo = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))[-1]
    if angulo > 45:
        angulo -= 90
    return float(angulo) if abs(angulo) < 15 else 0.0


def enderezar(gris: np.ndarray) -> np.ndarray:
    angulo = angulo_inclinacion(gris)
    if abs(angulo) < 0.3:
        return gris
    h, w = gris.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angulo, 1.0)
    return cv2.warpAffine(gris, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def nitidez(gris: np.ndarray) -> float:
    """Varianza del Laplaciano: valores bajos = foto borrosa. Sirve como regla de calidad."""
    return float(cv2.Laplacian(gris, cv2.CV_64F).var())


def preparar_para_ocr(img: np.ndarray) -> tuple[np.ndarray, dict]:
    gris = a_grises(img)
    gris = recortar_papel(gris)
    gris = enderezar(gris)
    metricas = {"nitidez": round(nitidez(gris), 1)}
    # agrandar ayuda a Tesseract con letra chica de impresora térmica
    if gris.shape[1] < 1000:
        gris = cv2.resize(gris, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gris = cv2.fastNlMeansDenoising(gris, h=10)
    # binarización adaptativa: soporta iluminación desigual
    binaria = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 15)
    return binaria, metricas
