"""
Modelos del dominio "Conferencia y configuración".

Este archivo define la tabla "conferencia" del modelo relacional del Sprint 0:
cada fila es una edición del evento, con sus fechas y los plazos de cada
etapa del proceso científico (HU-13).

Orden de las etapas (se valida en el serializador y en la base de datos):

    fecha_inicio_postulacion < limite_postulacion < limite_revision
                              < limite_correccion < limite_version_final
                                                                      |
                                       antes del día de fecha_inicio_evento
                                                                      |
                                        fecha_inicio_evento <= fecha_fin_evento

Los campos de la jornada de la agenda (hora_inicio_jornada, almuerzo,
duracion_presentacion_min y agenda_publicada) también están en la entidad
CONFERENCIA del modelo relacional, pero se agregan con su propia migración
en la historia de usuario de la agenda, que es la que los usa.
"""

from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class ConferenciaQuerySet(models.QuerySet):
    """Consultas de la tabla "conferencia"."""

    def vigente(self):
        """
        Devuelve la edición vigente de la conferencia, o None si no hay.

        La edición vigente es la próxima que todavía no ha terminado: la de
        fecha de inicio más cercana entre las que tienen fecha_fin_evento de
        hoy en adelante. Así, cuando termina una edición, la siguiente pasa a
        ser la vigente sin que nadie tenga que marcarla.

        La usan la postulación (HU-14) y la edición de artículos (HU-20) para
        saber a qué edición pertenece un artículo y si el plazo sigue abierto.
        """
        # localdate() es la fecha de hoy en America/Bogota (TIME_ZONE en settings.py).
        return (
            self.filter(fecha_fin_evento__gte=timezone.localdate())
            .order_by("fecha_inicio_evento", "id")
            .first()
        )


class Conferencia(models.Model):
    """
    Edición de la conferencia (tabla "conferencia"), con sus plazos (HU-13).

    Los plazos son fecha y hora (timestamptz): una postulación cierra, por
    ejemplo, el 15 de marzo a las 23:59 de Colombia. Las fechas del evento son
    solo días (date), porque el horario de cada día lo define la agenda.
    """

    nombre = models.CharField("nombre", max_length=200)

    # --- Días del evento ---------------------------------------------------
    fecha_inicio_evento = models.DateField("fecha de inicio del evento")
    fecha_fin_evento = models.DateField("fecha de fin del evento")

    # --- Plazos de cada etapa ----------------------------------------------
    # Es nullable para conservar ediciones existentes; las nuevas se exigen en API.
    fecha_inicio_postulacion = models.DateTimeField(
        "inicio de postulación", null=True, blank=True
    )

    # Hasta cuándo los autores pueden postular y editar artículos (HU-14 y HU-20).
    limite_postulacion = models.DateTimeField("límite de postulación")

    # Hasta cuándo el comité puede evaluar los artículos.
    limite_revision = models.DateTimeField("límite de revisión")

    # Hasta cuándo los autores pueden subir la versión corregida.
    limite_correccion = models.DateTimeField("límite de corrección")

    # Hasta cuándo se recibe la versión final para la publicación.
    limite_version_final = models.DateTimeField("límite de versión final")

    # Manager con la consulta de la edición vigente: Conferencia.objects.vigente()
    objects = ConferenciaQuerySet.as_manager()

    class Meta:
        db_table = "conferencia"
        verbose_name = "conferencia"
        verbose_name_plural = "conferencias"
        ordering = ["-fecha_inicio_evento"]

        # Restricciones en la base de datos: aunque alguien guarde una
        # conferencia sin pasar por la API (panel de administración o
        # consola), PostgreSQL rechaza las fechas fuera de orden.
        # La comparación del límite de versión final con el día de inicio del
        # evento se hace solo en el serializador, porque compara una fecha con
        # hora contra un día y depende de la zona horaria de Colombia.
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(fecha_inicio_postulacion__isnull=True)
                    | Q(fecha_inicio_postulacion__lt=F("limite_postulacion"))
                ),
                name="ck_conferencia_inicio_postulacion_antes_limite",
            ),
            models.CheckConstraint(
                condition=Q(limite_postulacion__lt=F("limite_revision")),
                name="ck_conferencia_postulacion_antes_revision",
            ),
            models.CheckConstraint(
                condition=Q(limite_revision__lt=F("limite_correccion")),
                name="ck_conferencia_revision_antes_correccion",
            ),
            models.CheckConstraint(
                condition=Q(limite_correccion__lt=F("limite_version_final")),
                name="ck_conferencia_correccion_antes_version_final",
            ),
            models.CheckConstraint(
                condition=Q(fecha_inicio_evento__lte=F("fecha_fin_evento")),
                name="ck_conferencia_inicio_antes_fin_evento",
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.fecha_inicio_evento:%Y})"

    def postulacion_abierta(self):
        """
        Indica si todavía se pueden postular o editar artículos.

        Uso en la HU-14 y la HU-20:
            conferencia = Conferencia.objects.vigente()
            if conferencia is None or not conferencia.postulacion_abierta():
                -> rechazar con 400
        """
        return timezone.now() <= self.limite_postulacion
