"""
Configuración del panel administrativo para el dominio de artículos.
"""

from django.contrib import admin

from .models import Articulo, HistorialEstado, AutorArticulo


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


@admin.register(HistorialEstado)
class HistorialEstadoAdmin(admin.ModelAdmin):
    """Vista administrativa de la trazabilidad de estados de artículos."""

    list_display = (
        "id",
        "articulo",
        "estado_anterior",
        "estado_nuevo",
        "usuario",
        "fecha_cambio",
    )
    list_filter = ("estado_nuevo",)
    search_fields = ("articulo__titulo", "usuario__correo")


@admin.register(AutorArticulo)
class AutorArticuloAdmin(admin.ModelAdmin):
    """Vista administrativa de los coautores/firmantes por artículo."""

    list_display = (
        "id",
        "articulo",
        "orden_firma",
        "nombre_completo",
        "correo",
        "afiliacion",
    )
    list_filter = ("articulo",)
    search_fields = ("nombre_completo", "correo", "afiliacion", "articulo__titulo")