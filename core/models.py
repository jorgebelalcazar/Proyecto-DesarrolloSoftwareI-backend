"""
Modelos compartidos entre los módulos del sistema.

La app "core" guarda lo que usan varios módulos al mismo tiempo.
Por ahora contiene el catálogo de líneas temáticas de la conferencia.
"""

from django.db import models


class LineaTematica(models.Model):
    """
    Catálogo de líneas temáticas de la conferencia (tabla "linea_tematica").

    Se comparte entre módulos:
      - Artículos: cada artículo pertenece a una línea temática.
      - Agenda: cada sesión agrupa artículos de una misma línea.
      - Usuarios: los miembros del comité se especializan en una o varias líneas.

    Las 5 líneas del enunciado se cargan automáticamente con la migración
    de datos "usuarios/0002_datos_iniciales".
    """

    # Nombre de la línea temática.
    # unique=True hace que la base de datos rechace dos líneas con el mismo nombre.
    nombre = models.CharField("nombre", max_length=100, unique=True)

    class Meta:
        # Nombre de la tabla en PostgreSQL, igual al del modelo relacional.
        # Sin esta línea, Django la llamaría "core_lineatematica".
        db_table = "linea_tematica"

        # Nombres que se muestran en el panel de administración.
        verbose_name = "línea temática"
        verbose_name_plural = "líneas temáticas"

        # Orden por defecto de las consultas: alfabético por nombre.
        ordering = ["nombre"]

    def __str__(self):
        # Texto que representa al objeto en el panel y en la consola.
        return self.nombre


class CriterioEvaluacion(models.Model):
    """Criterio editable de la rúbrica para evaluar artículos."""

    nombre = models.CharField("nombre", max_length=120, unique=True)
    descripcion = models.TextField("descripción", blank=True)
    peso = models.PositiveSmallIntegerField("peso porcentual")
    orden = models.PositiveSmallIntegerField("orden", default=1)
    activo = models.BooleanField("activo", default=True)

    class Meta:
        db_table = "criterio_evaluacion"
        verbose_name = "criterio de evaluación"
        verbose_name_plural = "criterios de evaluación"
        ordering = ["orden", "id"]
        constraints = [models.CheckConstraint(
            condition=models.Q(peso__lte=100),
            name="ck_criterio_evaluacion_peso_max_100",
        )]

    def __str__(self):
        return self.nombre
