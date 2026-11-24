"""
Modelos del dominio de artículos.

Este archivo define las tablas del modelo relacional del Sprint 0 para la
postulación de artículos:
  - articulo:         artículo postulado por un autor responsable (HU-14).
  - historial_estado: trazabilidad de cada cambio de estado del artículo.
  - autor_articulo:   coautores o firmantes del artículo (HU-15).
  - version_articulo: archivos PDF del artículo (HU-16).

Más adelante se agrega, con su migración y en su historia de usuario:
  - ruta_copyright de la versión final.
"""

from django.conf import settings
from django.db import models, transaction
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


class ArticuloYaDeshabilitado(Exception):
    """El artículo ya estaba deshabilitado: la deshabilitación no se repite (HU-21)."""


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

    # --- Deshabilitación por el comité (HU-21) --------------------------------
    # Un artículo deshabilitado sale de la conferencia para siempre: no se
    # borra (el registro científico se conserva) y no se puede rehabilitar.
    habilitado = models.BooleanField("habilitado", default=True)
    motivo_deshabilitacion = models.TextField("motivo de la deshabilitación", blank=True)
    fecha_deshabilitacion = models.DateTimeField(
        "fecha de la deshabilitación", null=True, blank=True
    )

    class Meta:
        db_table = "articulo"
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["-fecha_postulacion"]

        # Regla en la base de datos (HU-21): las columnas de la deshabilitación
        # siempre van de acuerdo con el estado. O el artículo está habilitado
        # y no tiene motivo ni fecha, o está DESHABILITADO con motivo y fecha.
        # Así nunca queda un artículo "a medias".
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(habilitado=True, motivo_deshabilitacion="", fecha_deshabilitacion=None)
                    & ~Q(estado="DESHABILITADO")
                ) | (
                    Q(habilitado=False, estado="DESHABILITADO", fecha_deshabilitacion__isnull=False)
                    & ~Q(motivo_deshabilitacion="")
                ),
                name="ck_articulo_deshabilitacion_coherente",
            ),
        ]

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

    def deshabilitar(self, usuario, motivo):
        """
        Retira el artículo de la conferencia de forma permanente (HU-21).

        En una sola transacción:
          1. Pasa el artículo a DESHABILITADO, con habilitado=False, el motivo
             y la fecha. No hay DELETE: el registro se conserva (criterio 2).
          2. Guarda en el historial quién lo hizo, cuándo, desde qué estado
             y por qué (criterio 3).

        Es irreversible: no existe la operación contraria, y si el artículo
        ya estaba deshabilitado lanza ArticuloYaDeshabilitado.

        select_for_update() bloquea la fila mientras dura la transacción: si
        dos miembros del comité lo deshabilitan al mismo tiempo, el segundo
        espera, ve el estado ya cambiado y recibe el error, en lugar de dejar
        dos filas en el historial.
        """
        with transaction.atomic():
            actual = Articulo.objects.select_for_update().get(pk=self.pk)
            if actual.estado == self.Estado.DESHABILITADO:
                raise ArticuloYaDeshabilitado("El artículo ya está deshabilitado.")

            estado_anterior = actual.estado
            self.estado = self.Estado.DESHABILITADO
            self.habilitado = False
            self.motivo_deshabilitacion = motivo
            self.fecha_deshabilitacion = timezone.now()
            self.save(update_fields=[
                "estado", "habilitado", "motivo_deshabilitacion", "fecha_deshabilitacion",
            ])

            HistorialEstado.objects.create(
                articulo=self,
                usuario=usuario,
                estado_anterior=estado_anterior,
                estado_nuevo=self.Estado.DESHABILITADO,
                observacion=motivo,
            )


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
    """
    Coautor o firmante de un artículo (tabla "autor_articulo").

    Guarda el nombre, la afiliación y el correo de cada investigador que firma
    el artículo, SIN exigir que tenga cuenta en el sistema (HU-15, criterio 1):
    por eso no tiene llave foránea a "usuario".

    "orden" es la posición de la firma (1, 2, 3...): el orden en que aparecen
    los nombres en el artículo publicado.
    """

    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.CASCADE,
        related_name="coautores",
        verbose_name="artículo",
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

        # Reglas también en la base de datos (HU-15, criterio 3):
        #   - un correo no se repite dentro del mismo artículo;
        #   - dos firmantes no ocupan la misma posición;
        #   - las posiciones empiezan en 1.
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
# VERSIONES DEL ARCHIVO PDF DEL ARTÍCULO (HU-16)
# ---------------------------------------------------------------------------
class VersionArticulo(models.Model):
    """
    Archivo PDF de una versión del artículo (tabla "version_articulo").

    Un artículo entrega varias versiones durante la conferencia:
      - INICIAL:    el manuscrito de la postulación (HU-16). Siempre es la número 1.
      - CORRECCION: la versión corregida después de la revisión.
      - FINAL:      la versión final para la publicación.

    El PDF NO se guarda en la base de datos: está en un bucket PRIVADO de
    Supabase Storage. Aquí solo se guarda su ruta dentro del bucket
    ("ruta_pdf"). Como el bucket es privado, la ruta no sirve para abrir el
    archivo directamente: el detalle del artículo (HU-19) genera, a partir
    de ella, un enlace firmado que vence a los pocos minutos.
    """

    class Tipo(models.TextChoices):
        INICIAL = "INICIAL", "Inicial"
        CORRECCION = "CORRECCION", "Corrección"
        FINAL = "FINAL", "Final"

    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.CASCADE,
        related_name="versiones",
        verbose_name="artículo",
    )
    tipo = models.CharField("tipo", max_length=20, choices=Tipo.choices)

    # Número consecutivo de la versión dentro del artículo: 1, 2, 3...
    numero = models.PositiveSmallIntegerField("número de versión")

    # Ruta del archivo dentro del bucket, por ejemplo "articulos/7/<uuid>.pdf".
    ruta_pdf = models.CharField("ruta del PDF", max_length=500)

    fecha_subida = models.DateTimeField("fecha de subida", auto_now_add=True)

    class Meta:
        db_table = "version_articulo"
        verbose_name = "versión del artículo"
        verbose_name_plural = "versiones del artículo"
        ordering = ["articulo", "numero"]

        # Reglas también en la base de datos (HU-16, criterio 2):
        #   - un artículo no repite un número de versión;
        #   - los números empiezan en 1;
        #   - la versión INICIAL es siempre la número 1. Junto con la primera
        #     regla, esto impide que un artículo tenga dos versiones iniciales.
        constraints = [
            models.UniqueConstraint(
                fields=["articulo", "numero"], name="uk_version_articulo_numero"
            ),
            models.CheckConstraint(
                condition=Q(numero__gte=1), name="ck_version_articulo_numero_positivo"
            ),
            models.CheckConstraint(
                condition=~Q(tipo="INICIAL") | Q(numero=1),
                name="ck_version_articulo_inicial_es_la_uno",
            ),
        ]

    def __str__(self):
        return f"Artículo #{self.articulo_id}, versión {self.numero} ({self.get_tipo_display()})"