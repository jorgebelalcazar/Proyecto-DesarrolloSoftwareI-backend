"""
Configuración del panel administrativo para el dominio de artículos.
"""

from django.contrib import admin

from .models import Articulo


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    """Vista administrativa de artículos postulados."""

    list_display = (
        "id",
        "titulo",
        "linea_tematica",
        "autor_responsable",
        "estado",
        "fecha_postulacion",
    )
    list_filter = ("estado", "linea_tematica")
    search_fields = ("titulo", "palabras_clave", "autor_responsable__correo")