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