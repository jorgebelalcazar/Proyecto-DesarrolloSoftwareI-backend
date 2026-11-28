"""
Modelos del proceso de revisión y arbitraje (Épica 3, Sprint 3).

Este archivo define las dos tablas que comparten las HU-24 a HU-29:
  - revision:     un jurado (miembro del Comité) asignado a un artículo,
                  con su decisión y sus comentarios (HU-25, HU-26, HU-28).
  - calificacion: el puntaje que ese jurado da en cada criterio de la
                  rúbrica de la conferencia (HU-28).

Reglas que viven en la base de datos (Meta.constraints):
  - un jurado no se asigna dos veces al mismo artículo;
  - una revisión PENDIENTE no tiene decisión ni fecha de entrega, y una
    COMPLETADA tiene las dos;
  - un criterio se califica una sola vez en cada revisión.

Reglas que NO caben en una restricción de la base de datos, porque cruzan
varias filas o tablas, y que validan los servicios de cada historia:
  - un artículo tiene exactamente 3 jurados (HU-25 y HU-26);
  - el jurado tiene el rol Comité y no es autor ni coautor del artículo
    (HU-25 y HU-26);
  - el puntaje no supera el puntaje máximo del criterio (HU-28).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from articulos.models import Articulo
from conferencias.models import CriterioEvaluacion


# ---------------------------------------------------------------------------
# REVISIÓN (asignación de un jurado a un artículo)
# ---------------------------------------------------------------------------
class Revision(models.Model):
    """
    Asignación de un jurado a un artículo y su evaluación (tabla "revision").

    Nace PENDIENTE cuando el Comité asigna al jurado (HU-25 automática o
    HU-26 manual). Pasa a COMPLETADA cuando el jurado registra su evaluación
    (HU-28): en ese momento quedan la decisión, los comentarios y la fecha
    de entrega. Con 3 revisiones completadas se calcula el veredicto (HU-29).
    """

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        COMPLETADA = "COMPLETADA", "Completada"

    class Decision(models.TextChoices):
        # Es el voto del jurado. El estado del ARTÍCULO se llama APROBADO;
        # la HU-29 traduce: mayoría de ACEPTADO -> artículo APROBADO.
        ACEPTADO = "ACEPTADO", "Aceptado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    # --- Relaciones ---------------------------------------------------------
    # on_delete=PROTECT: un artículo o un jurado con revisiones no se puede
    # borrar; las evaluaciones son parte del registro científico del evento.
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name="revisiones",
        verbose_name="artículo",
    )
    revisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="revisiones",
        verbose_name="jurado",
    )

    # Miembro del Comité que hizo la asignación (automática o manual).
    # Deja constancia de quién asignó a cada jurado (HU-26, criterio 3).
    # SET_NULL: si algún día se borra ese usuario, la revisión se conserva.
    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisiones_asignadas",
        verbose_name="asignado por",
    )

    # --- Estado y evaluación ------------------------------------------------
    estado = models.CharField(
        "estado", max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )

    # Vacía mientras la revisión está PENDIENTE (regla en Meta.constraints).
    decision = models.CharField(
        "decisión", max_length=20, choices=Decision.choices, blank=True, default=""
    )

    # Retroalimentación del jurado para el autor (obligatoria en la HU-28).
    comentarios = models.TextField("comentarios", blank=True, default="")

    # --- Fechas -------------------------------------------------------------
    fecha_asignacion = models.DateTimeField("fecha de asignación", auto_now_add=True)
    fecha_entrega = models.DateTimeField("fecha de entrega", null=True, blank=True)

    class Meta:
        db_table = "revision"
        verbose_name = "revisión"
        verbose_name_plural = "revisiones"
        ordering = ["articulo", "id"]

        # Reglas también en la base de datos:
        #   - un jurado no se asigna dos veces al mismo artículo (HU-25, criterio 3);
        #   - PENDIENTE: sin decisión y sin fecha de entrega;
        #     COMPLETADA: con decisión válida y con fecha de entrega.
        constraints = [
            models.UniqueConstraint(
                fields=["articulo", "revisor"], name="uk_revision_articulo_revisor"
            ),
            models.CheckConstraint(
                condition=(
                    Q(estado="PENDIENTE", decision="", fecha_entrega__isnull=True)
                    | Q(
                        estado="COMPLETADA",
                        decision__in=["ACEPTADO", "RECHAZADO"],
                        fecha_entrega__isnull=False,
                    )
                ),
                name="ck_revision_estado_coherente",
            ),
        ]
        indexes = [
            # La bandeja del jurado (HU-27) y el balanceo de carga (HU-25)
            # consultan por jurado y estado.
            models.Index(fields=["revisor", "estado"], name="ix_revision_revisor_estado"),
        ]

    def __str__(self):
        return f"Artículo #{self.articulo_id} — jurado {self.revisor} ({self.get_estado_display()})"

    @property
    def completada(self):
        """Indica si el jurado ya entregó su evaluación."""
        return self.estado == self.Estado.COMPLETADA


# ---------------------------------------------------------------------------
# CALIFICACIÓN (puntaje de un criterio de la rúbrica)
# ---------------------------------------------------------------------------
class Calificacion(models.Model):
    """
    Puntaje que un jurado da a un criterio de la rúbrica (tabla "calificacion").

    Cada revisión completada tiene una calificación por cada criterio de la
    rúbrica de su conferencia (HU-22.2). La HU-28 valida que el puntaje no
    supere el puntaje máximo del criterio.
    """

    # on_delete=CASCADE: las calificaciones no existen sin su revisión.
    revision = models.ForeignKey(
        Revision,
        on_delete=models.CASCADE,
        related_name="calificaciones",
        verbose_name="revisión",
    )

    # on_delete=PROTECT: un criterio ya usado para calificar no se puede
    # borrar; cambiaría el resultado de evaluaciones ya entregadas.
    criterio = models.ForeignKey(
        CriterioEvaluacion,
        on_delete=models.PROTECT,
        related_name="calificaciones",
        verbose_name="criterio",
    )

    # Entero desde 0. PositiveSmallIntegerField ya impide negativos.
    puntaje = models.PositiveSmallIntegerField("puntaje")

    class Meta:
        db_table = "calificacion"
        verbose_name = "calificación"
        verbose_name_plural = "calificaciones"
        ordering = ["revision", "criterio"]

        # Un criterio se califica una sola vez en cada revisión.
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "criterio"], name="uk_calificacion_revision_criterio"
            ),
        ]

    def __str__(self):
        return f"{self.criterio.nombre}: {self.puntaje}/{self.criterio.puntaje_maximo}"