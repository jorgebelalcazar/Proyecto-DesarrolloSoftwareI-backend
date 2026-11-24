"""
Registro de los catálogos compartidos en el panel de administración.

El panel (/admin/) permite consultar las tablas del sistema desde el navegador
sin escribir SQL. Solo pueden entrar los administradores.
"""

from django.contrib import admin

from .models import CriterioEvaluacion, LineaTematica


# @admin.register conecta el modelo con su configuración en el panel.
@admin.register(LineaTematica)
class LineaTematicaAdmin(admin.ModelAdmin):
    # Columnas que se muestran en la lista.
    list_display = ("nombre",)

    # Habilita el buscador por nombre.
    search_fields = ("nombre",)


@admin.register(CriterioEvaluacion)
class CriterioEvaluacionAdmin(admin.ModelAdmin):
    """Permite al equipo configurar los criterios sin cambiar código."""

    list_display = ("nombre", "peso", "orden", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "descripcion")
    ordering = ("orden", "id")
