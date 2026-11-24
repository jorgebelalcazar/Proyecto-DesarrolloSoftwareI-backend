"""
Modelos del dominio de artículos.

Este archivo define las tablas del modelo relacional del Sprint 0 para la
postulación de artículos:
  - articulo:         artículo postulado por un autor responsable (HU-14).
  - historial_estado: trazabilidad de cada cambio de estado del artículo.
  - autor_articulo:   coautores o firmantes del artículo (HU-15).

Más adelante se agregan, cada una con su migración y en su historia de usuario:
  - version_articulo: archivos PDF del artículo (HU-16).
  - habilitado, motivo_deshabilitacion y fecha_deshabilitacion (HU-21).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def mensaje_plazo_vencido(conferencia):
    """
    Mensaje para cuando ya pasó el límite de postulación de una edición.

    Lo usan la postulación (HU-14) y la edición de coautores (HU-15), y lo
    usará la edición del artículo (HU-20). La fecha se muestra en hora de
    Colombia: "El plazo de postulación de Nexo 2027 venció el 15/03/2027 a las 23:59."
    """
    limite = timezone.localtime(conferencia.limite_postulacion)
    return (
        f"El plazo de postulación de {conferencia.nombre} venció el "
        f"{limite:%d/%m/%Y} a las {limite:%H:%M}."
    )


# ---------------------------------------------------------------------------
# ARTÍCULO
# ---------------------------------------------------------------------------
class Articulo(models.Model):
    """
    Artículo científico postulado a una edición de la conferencia (tabla "articulo").

    Pertenece a una edición (conferencia), a una de las 5 líneas temáticas
    oficiales y a un autor responsable: el usuario que lo postula. Nace en
    estado POSTULADO (HU-14.1).
    """

    class Estado(models.TextChoices):
        POSTULADO = "POSTULADO", "Postulado"
        EN_REVISION = "EN_REVISION", "En revisión"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        DESHABILITADO = "DESHABILITADO", "Deshabilitado"

    # --- Relaciones ---------------------------------------------------------
    # on_delete=PROTECT: no se puede borrar una edición, una línea temática ni
    # un usuario mientras tengan artículos. Los artículos son el registro
    # científico de la conferencia y no deben quedar huérfanos.
    conferencia = models.ForeignKey(
        "conferencias.Conferencia",
        on_delete=models.PROTECT,
        related_name="articulos",
        verbose_name="conferencia",
    )
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

    # --- Metadatos (HU-14) ----------------------------------------------------
    # Las longitudes de las columnas siguen el modelo relacional. Los límites
    # del negocio (título de 200 caracteres y resumen de 300 palabras) los
    # valida el serializador, que es donde se responde el error al usuario.
    titulo = models.CharField("título", max_length=300)
    resumen = models.TextField("resumen")
    palabras_clave = models.CharField("palabras clave", max_length=300)

    # --- Estado ---------------------------------------------------------------
    estado = models.CharField(
        "estado", max_length=30, choices=Estado.choices, default=Estado.POSTULADO
    )

    # auto_now_add=True: Django pone la fecha automáticamente al crear el registro.
    fecha_postulacion = models.DateTimeField("fecha de postulación", auto_now_add=True)

    class Meta:
        db_table = "articulo"
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["-fecha_postulacion"]

    def __str__(self):
        return f"{self.titulo} ({self.get_estado_display()})"

    def motivo_no_editable(self):
        """
        Indica por qué el autor ya no puede modificar el artículo, o None si sí puede.

        Un artículo se puede modificar (coautores en la HU-15, metadatos en la
        HU-20) mientras:
          - no esté DESHABILITADO por el comité (HU-21);
          - siga abierto el plazo de postulación de SU edición (HU-13).
        """
        if self.estado == self.Estado.DESHABILITADO:
            return "El artículo está deshabilitado y ya no se puede modificar."
        if not self.conferencia.postulacion_abierta():
            return mensaje_plazo_vencido(self.conferencia)
        return None


# ---------------------------------------------------------------------------
# HISTORIAL DE ESTADOS DEL ARTÍCULO
# ---------------------------------------------------------------------------
class HistorialEstado(models.Model):
    """
    Cambio de estado de un artículo (tabla "historial_estado").

    Cada vez que un artículo nace (HU-14.2) o cambia de estado (por ejemplo,
    al deshabilitarlo en la HU-21), se guarda una fila con el estado anterior,
    el nuevo, quién hizo el cambio, cuándo y por qué. Es la trazabilidad que
    pide el enunciado: nunca se edita ni se borra.
    """

    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.CASCADE,
        related_name="historial",
        verbose_name="artículo",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cambios_estado_articulo",
        verbose_name="usuario",
    )

    # Vacío en la primera fila: un artículo recién postulado no tenía estado.
    estado_anterior = models.CharField(
        "estado anterior", max_length=30, choices=Articulo.Estado.choices, blank=True
    )
    estado_nuevo = models.CharField(
        "estado nuevo", max_length=30, choices=Articulo.Estado.choices
    )
    observacion = models.TextField("observación", blank=True)
    fecha = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        db_table = "historial_estado"
        verbose_name = "cambio de estado"
        verbose_name_plural = "historial de estados"
        ordering = ["fecha", "id"]

    def __str__(self):
        origen = self.estado_anterior or "INICIO"
        return f"Artículo #{self.articulo_id}: {origen} -> {self.estado_nuevo}"


# ---------------------------------------------------------------------------
# COAUTORES O FIRMANTES DEL ARTÍCULO (HU-15)
# ---------------------------------------------------------------------------
class AutorArticulo(models.Model):
    """Coautor o firmante sin necesidad de cuenta en el sistema."""

    articulo = models.ForeignKey(
        Articulo, on_delete=models.CASCADE, related_name="coautores", verbose_name="artículo"
    )
    nombre_completo = models.CharField("nombre completo", max_length=200)
    afiliacion = models.CharField("afiliación", max_length=200)
    correo = models.EmailField("correo electrónico", max_length=254)
    orden = models.PositiveSmallIntegerField("orden de firma")

    class Meta:
        db_table = "autor_articulo"
        verbose_name = "coautor del artículo"
        verbose_name_plural = "coautores del artículo"
        ordering = ["orden"]
        constraints = [
            models.UniqueConstraint(
                fields=["articulo", "correo"], name="uk_autor_articulo_correo"
            ),
            models.UniqueConstraint(
                fields=["articulo", "orden"], name="uk_autor_articulo_orden"
            ),
            models.CheckConstraint(
                condition=Q(orden__gte=1), name="ck_autor_articulo_orden_positivo"
            ),
        ]

    def __str__(self):
        return f"{self.orden}. {self.nombre_completo} <{self.correo}>"


# ---------------------------------------------------------------------------
# VERSIONES DEL ARCHIVO DEL ARTÍCULO (HU-16)
# ---------------------------------------------------------------------------
class VersionArticulo(models.Model):
    """Archivo entregado para una versión de un artículo (HU-16)."""

    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.CASCADE,
        related_name="versiones",
        verbose_name="artículo",
    )
    numero_version = models.PositiveSmallIntegerField("número de versión")
    ruta_archivo = models.CharField("ruta privada del archivo", max_length=500)
    cargado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="versiones_articulo_cargadas",
        verbose_name="cargado por",
    )
    fecha_carga = models.DateTimeField("fecha de carga", auto_now_add=True)

    class Meta:
        db_table = "version_articulo"
        verbose_name = "versión de artículo"
        verbose_name_plural = "versiones de artículo"
        ordering = ["articulo_id", "numero_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["articulo", "numero_version"],
                name="uniq_version_articulo_numero",
            ),
        ]

    def __str__(self):
        return f"Artículo #{self.articulo_id}, versión {self.numero_version}"