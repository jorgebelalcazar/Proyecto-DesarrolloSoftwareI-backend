"""
Modelos del dominio de artículos científicos.

Este archivo define las tablas del módulo de Gestión y Envío de Artículos:
- articulo: artículos postulados por un autor responsable (HU-14).
"""

from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# ARTÍCULO
# ---------------------------------------------------------------------------
class Articulo(models.Model):
    """
    Artículo científico postulado a la conferencia (tabla "articulo").

    Cada artículo pertenece a una de las 5 líneas temáticas oficiales,
    queda vinculado al usuario que lo postula como autor responsable y
    nace con estado inicial POSTULADO (HU-14.1).
    """

    class Estado(models.TextChoices):
        POSTULADO = "POSTULADO", "Postulado"
        EN_REVISION = "EN_REVISION", "En revisión"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        DESHABILITADO = "DESHABILITADO", "Deshabilitado"

    # --- Metadatos del artículo (HU-14) ----------------------------------
    titulo = models.CharField("título", max_length=200)
    resumen = models.TextField("resumen")
    palabras_clave = models.CharField("palabras clave", max_length=255)

    # --- Clasificación y autoría -----------------------------------------
    linea_tematica = models.ForeignKey(
        "core.LineaTematica",
        on_delete=models.PROTECT,
        related_name="articulos",
        verbose_name="línea temática",
    )

    # En la base de datos crea la columna "autor_responsable_id".
    autor_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="articulos_responsable",
        verbose_name="autor responsable",
    )

    # --- Estado y trazabilidad -------------------------------------------
    estado = models.CharField(
        "estado",
        max_length=20,
        choices=Estado.choices,
        default=Estado.POSTULADO,
    )
    fecha_postulacion = models.DateTimeField(
        "fecha de postulación", auto_now_add=True
    )
    fecha_actualizacion = models.DateTimeField(
        "fecha de actualización", auto_now=True
    )
    observacion_deshabilitacion = models.TextField(
        "observación de deshabilitación", blank=True
    )

    class Meta:
        db_table = "articulo"
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["-fecha_postulacion"]

    def __str__(self):
        return f"{self.titulo} ({self.get_estado_display()})"